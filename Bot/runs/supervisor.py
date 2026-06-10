"""
Run supervisor.

Long-lived process that lives inside the bot container and owns child run
processes (backtest / paper / live). The API never spawns processes directly;
it inserts rows into ``run_commands`` and a PostgreSQL trigger fires a
``run_command`` NOTIFY. The supervisor listens for those notifications (with a
periodic poll as a reliable fallback), claims each command atomically, and:

- **start**: validates the params again (defense in depth), spawns
  ``python -m main <run_type> ... --run-id <id>`` with stdout/stderr redirected
  to a per-run log file, and records the child PID on the run row.
- **stop**: sends SIGTERM so the bot shuts down gracefully (closes positions,
  writes a terminal run status).
- **kill**: sends SIGKILL — **backtest only** (paper/live must stop gracefully).

It also reconciles state on startup (a crash must not orphan running runs) and
reaps exited children.

Design notes / security:
- Commands are claimed with an atomic ``UPDATE ... WHERE processed_at IS NULL``
  so a NOTIFY + poll race (or a restart replay) executes each command once.
- Every parameter that becomes an argv entry is re-validated here against a
  strict allowlist; the subprocess is launched with ``create_subprocess_exec``
  (no shell), so neither shell metacharacters nor flag-like values can inject.
"""

import asyncio
import logging
import os
import re
import signal
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Optional

import asyncpg

logger = logging.getLogger(__name__)

# --- allowlists (independent copy from the API; defense in depth) -----------

_SYMBOL_RE = re.compile(r"^[A-Z]{2,10}USDC$")
_ALLOWED_TIMEFRAMES = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h", "1d",
}
_ALLOWED_ENGINES = {"vectorbt", "event_driven"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_RUN_TYPES = {"backtest", "paper", "live"}

NOTIFY_CHANNEL = "run_command"
POLL_INTERVAL_SECONDS = 30
REAPER_INTERVAL_SECONDS = 10


class CommandValidationError(ValueError):
    """Raised when a run_commands payload fails the supervisor's allowlist."""


@dataclass
class Child:
    """A tracked run process."""

    run_id: int
    run_type: str
    pid: int
    process: Optional[asyncio.subprocess.Process] = None  # None when reconciled, not spawned
    log_fh: Optional[IO[bytes]] = field(default=None, repr=False)

    def is_alive(self) -> bool:
        if self.process is not None:
            return self.process.returncode is None
        # Reconciled child: probe the pid.
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False


def _validate_start_params(params: dict[str, Any]) -> dict[str, Any]:
    """Re-validate a start payload and return a clean copy, or raise."""
    if not isinstance(params, dict):
        raise CommandValidationError("params must be an object")

    run_type = params.get("run_type")
    if run_type not in _RUN_TYPES:
        raise CommandValidationError(f"invalid run_type: {run_type!r}")

    symbol = str(params.get("symbol", ""))
    if not _SYMBOL_RE.fullmatch(symbol):
        raise CommandValidationError(f"invalid symbol: {symbol!r}")

    timeframe = str(params.get("timeframe", ""))
    if timeframe not in _ALLOWED_TIMEFRAMES:
        raise CommandValidationError(f"invalid timeframe: {timeframe!r}")

    clean: dict[str, Any] = {"run_type": run_type, "symbol": symbol, "timeframe": timeframe}

    if run_type == "backtest":
        for key in ("start_date", "end_date"):
            val = params.get(key)
            if not isinstance(val, str) or not _DATE_RE.fullmatch(val):
                raise CommandValidationError(f"invalid {key}: {val!r}")
            clean[key] = val
        capital = params.get("initial_capital")
        if capital is not None:
            if not isinstance(capital, (int, float)) or capital <= 0:
                raise CommandValidationError(f"invalid initial_capital: {capital!r}")
            clean["initial_capital"] = float(capital)
        engine = params.get("engine")
        if engine is not None:
            if engine not in _ALLOWED_ENGINES:
                raise CommandValidationError(f"invalid engine: {engine!r}")
            clean["engine"] = engine
        wsid = params.get("weights_set_id")
        if wsid is not None:
            if not isinstance(wsid, str) or not _UUID_RE.fullmatch(wsid):
                raise CommandValidationError(f"invalid weights_set_id: {wsid!r}")
            clean["weights_set_id"] = wsid
        clean["save"] = bool(params.get("save", True))

    elif run_type == "live":
        testnet = params.get("testnet")
        if not isinstance(testnet, bool):
            raise CommandValidationError("live requires boolean 'testnet'")
        clean["testnet"] = testnet

    return clean


def _build_argv(run_id: int, params: dict[str, Any]) -> list[str]:
    """Build the validated argv for the child process (no shell)."""
    run_type = params["run_type"]
    argv = [
        sys.executable, "-m", "main", run_type,
        "--symbol", params["symbol"],
        "--timeframe", params["timeframe"],
        "--run-id", str(run_id),
    ]

    if run_type == "backtest":
        argv += ["--start-date", params["start_date"], "--end-date", params["end_date"]]
        if "initial_capital" in params:
            argv += ["--initial-capital", str(params["initial_capital"])]
        if "engine" in params:
            argv += ["--engine", params["engine"]]
        if params.get("weights_set_id"):
            argv += ["--weights-set-id", params["weights_set_id"]]
        if params.get("save", True):
            argv += ["--save"]
    elif run_type == "live":
        if params.get("testnet"):
            argv += ["--testnet"]
        # No interactive TTY: pre-confirm. The bot only honours --confirm on
        # mainnet; the API already enforced the 'I UNDERSTAND' gate.
        argv += ["--confirm"]

    return argv


class RunSupervisor:
    """Owns child run processes driven by the ``run_commands`` channel."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        dsn: str,
        log_dir: str,
        max_concurrent_backtests: int = 2,
    ):
        self.db_pool = db_pool
        self.dsn = dsn
        self.log_dir = Path(log_dir)
        self.max_concurrent_backtests = max_concurrent_backtests
        self.instance_id = f"{socket.gethostname()}:{os.getpid()}"
        self.children: dict[int, Child] = {}
        self._listen_conn: Optional[asyncpg.Connection] = None
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()  # set by NOTIFY to trigger an immediate drain

    # -- lifecycle -----------------------------------------------------------

    async def run(self) -> None:
        """Main supervisor loop: reconcile, then listen + poll + reap until stopped."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"RunSupervisor starting (instance={self.instance_id}, log_dir={self.log_dir})")

        await self._reconcile_on_startup()
        await self._start_listener()

        reaper = asyncio.create_task(self._reaper_loop(), name="supervisor-reaper")
        try:
            await self._command_loop()
        finally:
            reaper.cancel()
            await self._stop_listener()
            logger.info("RunSupervisor stopped")

    def request_stop(self) -> None:
        """Signal the supervisor loops to exit (children keep running)."""
        self._stop_event.set()
        self._wake_event.set()

    async def _start_listener(self) -> None:
        try:
            self._listen_conn = await asyncpg.connect(self.dsn)
            await self._listen_conn.add_listener(NOTIFY_CHANNEL, self._on_notify)
            logger.info(f"Listening on NOTIFY channel '{NOTIFY_CHANNEL}'")
        except Exception as e:
            logger.error(f"Failed to start NOTIFY listener (poll fallback still active): {e}")
            self._listen_conn = None

    async def _stop_listener(self) -> None:
        if self._listen_conn:
            try:
                await self._listen_conn.remove_listener(NOTIFY_CHANNEL, self._on_notify)
                await self._listen_conn.close()
            except Exception as e:
                logger.error(f"Error closing NOTIFY listener: {e}")
            self._listen_conn = None

    def _on_notify(self, *_args) -> None:
        # Just wake the loop; the actual work is an atomic claim against the table.
        self._wake_event.set()

    # -- command processing --------------------------------------------------

    async def _command_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._drain_pending()
            except Exception as e:
                logger.error(f"Error draining commands: {e}", exc_info=True)

            # Wait for a NOTIFY wake-up or the poll interval, whichever first.
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
            self._wake_event.clear()

    async def _drain_pending(self) -> None:
        """Claim and execute all currently pending commands (oldest first)."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, run_id, kind FROM run_commands "
                "WHERE status = 'pending' ORDER BY created_at ASC"
            )
        for row in rows:
            await self._process_command(row["id"])

    async def _process_command(self, command_id: int) -> None:
        """Atomically claim a single command and execute it."""
        async with self.db_pool.acquire() as conn:
            claimed = await conn.fetchrow(
                """
                UPDATE run_commands
                SET status = 'processed', processed_at = NOW(), processed_by = $2
                WHERE id = $1 AND processed_at IS NULL
                RETURNING run_id, kind, params
                """,
                command_id, self.instance_id,
            )
        if not claimed:
            return  # someone else (or a previous drain) already handled it

        run_id = claimed["run_id"]
        kind = claimed["kind"]
        params = claimed["params"]
        if isinstance(params, str):
            import json
            params = json.loads(params)

        try:
            if kind == "start":
                await self._handle_start(run_id, params or {})
            elif kind == "stop":
                await self._handle_stop(run_id)
            elif kind == "kill":
                await self._handle_kill(run_id)
            else:
                raise CommandValidationError(f"unknown command kind: {kind!r}")
        except Exception as e:
            logger.error(f"Command {command_id} ({kind}, run={run_id}) failed: {e}", exc_info=True)
            await self._mark_command_failed(command_id)
            if kind == "start":
                await self._mark_run_failed(run_id)

    async def _mark_command_failed(self, command_id: int) -> None:
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE run_commands SET status = 'failed' WHERE id = $1", command_id
                )
        except Exception as e:
            logger.error(f"Could not mark command {command_id} failed: {e}")

    async def _mark_run_failed(self, run_id: int) -> None:
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE runs SET status = 'failed', completed_at = NOW() "
                    "WHERE id = $1 AND status IN ('pending', 'running')",
                    run_id,
                )
        except Exception as e:
            logger.error(f"Could not mark run {run_id} failed: {e}")

    # -- handlers ------------------------------------------------------------

    async def _handle_start(self, run_id: int, params: dict[str, Any]) -> None:
        if run_id in self.children and self.children[run_id].is_alive():
            logger.warning(f"Start ignored: run {run_id} already has a live child")
            return

        clean = _validate_start_params(params)
        run_type = clean["run_type"]

        if run_type == "backtest":
            active = sum(1 for c in self.children.values() if c.run_type == "backtest" and c.is_alive())
            if active >= self.max_concurrent_backtests:
                raise RuntimeError(
                    f"max concurrent backtests ({self.max_concurrent_backtests}) reached"
                )

        argv = _build_argv(run_id, clean)
        log_path = self.log_dir / f"run_{run_id}.log"
        log_fh = open(log_path, "ab", buffering=0)

        logger.info(f"Spawning run {run_id} ({run_type}): {' '.join(argv[2:])}")
        process = await asyncio.create_subprocess_exec(
            *argv, stdout=log_fh, stderr=asyncio.subprocess.STDOUT,
        )

        self.children[run_id] = Child(
            run_id=run_id, run_type=run_type, pid=process.pid, process=process, log_fh=log_fh,
        )
        await self._record_pid(run_id, process.pid)

        # Reap asynchronously so we notice unexpected exits.
        asyncio.create_task(self._await_child(run_id), name=f"await-run-{run_id}")

    async def _handle_stop(self, run_id: int) -> None:
        child = self.children.get(run_id)
        if not child or not child.is_alive():
            logger.warning(f"Stop: no live child for run {run_id} (already exited?)")
            return
        logger.info(f"Sending SIGTERM to run {run_id} (pid={child.pid})")
        self._signal(child, signal.SIGTERM)

    async def _handle_kill(self, run_id: int) -> None:
        child = self.children.get(run_id)
        if not child:
            logger.warning(f"Kill: no child for run {run_id}")
            return
        if child.run_type != "backtest":
            # Belt-and-braces: the API already blocks this.
            raise RuntimeError("kill is only allowed for backtest runs")
        if not child.is_alive():
            return
        logger.info(f"Sending SIGKILL to backtest run {run_id} (pid={child.pid})")
        self._signal(child, signal.SIGKILL)

    def _signal(self, child: Child, sig: signal.Signals) -> None:
        try:
            if child.process is not None and child.process.returncode is None:
                child.process.send_signal(sig)
            else:
                os.kill(child.pid, sig)
        except ProcessLookupError:
            logger.info(f"Process for run {child.run_id} already gone")
        except Exception as e:
            logger.error(f"Failed to signal run {child.run_id}: {e}")

    # -- reaping & reconciliation -------------------------------------------

    async def _await_child(self, run_id: int) -> None:
        child = self.children.get(run_id)
        if not child or child.process is None:
            return
        rc = await child.process.wait()
        logger.info(f"Run {run_id} exited (rc={rc})")
        self._close_child(run_id)
        # Backtests that are SIGKILLed (rc<0) or crash won't set their own status.
        if rc != 0:
            await self._mark_run_failed(run_id)

    async def _reaper_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(REAPER_INTERVAL_SECONDS)
            for run_id, child in list(self.children.items()):
                if not child.is_alive():
                    logger.info(f"Reaping dead child for run {run_id}")
                    self._close_child(run_id)
                    await self._mark_run_failed(run_id)

    def _close_child(self, run_id: int) -> None:
        child = self.children.pop(run_id, None)
        if child and child.log_fh:
            try:
                child.log_fh.close()
            except Exception:
                pass

    async def _reconcile_on_startup(self) -> None:
        """After a supervisor restart, recover or fail orphaned running runs."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, run_type, supervisor_pid FROM runs WHERE status IN ('pending', 'running')"
            )
        for row in rows:
            run_id = row["id"]
            pid = row["supervisor_pid"]
            if pid and _pid_matches_run(pid, run_id):
                logger.info(f"Reconciled live child for run {run_id} (pid={pid})")
                self.children[run_id] = Child(run_id=run_id, run_type=row["run_type"], pid=pid)
            else:
                logger.warning(f"Run {run_id} has no live process; marking failed (orphaned)")
                await self._mark_run_failed(run_id)

    async def _record_pid(self, run_id: int, pid: int) -> None:
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("UPDATE runs SET supervisor_pid = $2 WHERE id = $1", run_id, pid)
        except Exception as e:
            logger.error(f"Could not record pid for run {run_id}: {e}")


def _pid_matches_run(pid: int, run_id: int) -> bool:
    """True if a live process with the given pid was started for this run_id.

    Verifies via ``/proc/<pid>/cmdline`` (Linux container) to avoid acting on a
    reused PID. Returns False if the pid is gone or the cmdline doesn't match.
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            cmdline = fh.read().split(b"\x00")
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False
    parts = [p.decode("utf-8", "replace") for p in cmdline if p]
    return "--run-id" in parts and str(run_id) in parts
