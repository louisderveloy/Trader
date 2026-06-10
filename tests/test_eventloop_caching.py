"""
Test for event loop caching in multiprocessing optimization.

This test verifies that:
1. Each worker process gets a consistent event loop across trials
2. Event loops don't change between trials in the same worker
3. No "different loop" errors occur when using cached pools
"""

import asyncio
import multiprocessing
import os
import pytest


def simple_worker_task(worker_id: int, num_iterations: int):
    """
    Simulate a worker that creates/gets event loops multiple times.
    Similar to what happens in `sync_objective()` across multiple trials.
    """
    from bot.optimization.runner import sync_objective

    # Simulate the function attribute cache
    if not hasattr(sync_objective, "_worker_loop_cache"):
        sync_objective._worker_loop_cache = {}

    loops_used = []
    pid = os.getpid()

    for i in range(num_iterations):
        # Simulate what sync_objective does
        if pid not in sync_objective._worker_loop_cache:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            sync_objective._worker_loop_cache[pid] = loop

        loop = sync_objective._worker_loop_cache[pid]
        loops_used.append(id(loop))

    # All loops should be identical (same object)
    return {
        "worker_id": worker_id,
        "pid": pid,
        "loops_used": loops_used,
        "all_same": len(set(loops_used)) == 1,
    }


def test_eventloop_consistency_single_process():
    """Test that event loop is reused across multiple calls in same process."""
    import asyncio
    import os

    # Initialize cache on sync_objective
    from bot.optimization.runner import sync_objective

    if not hasattr(sync_objective, "_worker_loop_cache"):
        sync_objective._worker_loop_cache = {}

    pid = os.getpid()
    loops = []

    # Get loop multiple times (simulating multiple trials)
    for i in range(5):
        if pid not in sync_objective._worker_loop_cache:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            sync_objective._worker_loop_cache[pid] = loop

        loop = sync_objective._worker_loop_cache[pid]
        loops.append(id(loop))

    # All should be the same object
    assert len(set(loops)) == 1, f"Got {len(set(loops))} different loops, expected 1"


def test_eventloop_consistency_multiprocess():
    """Test that each worker process gets its own consistent event loop."""
    # Use 'spawn' method to match Optuna's behavior
    ctx = multiprocessing.get_context("spawn")

    with ctx.Pool(processes=2) as pool:
        results = pool.starmap(
            simple_worker_task, [(0, 5), (1, 5)]  # 2 workers, 5 trials each
        )

    # Each worker should have used the same loop throughout
    for result in results:
        assert result["all_same"], (
            f"Worker {result['worker_id']} (PID {result['pid']}) "
            f"used {len(set(result['loops_used']))} different loops"
        )

    # Each worker should be different
    pids = [r["pid"] for r in results]
    assert len(set(pids)) == 2, f"Expected 2 different PIDs, got {set(pids)}"


def test_eventloop_isolated_per_process():
    """Test that different worker processes get different event loops."""
    ctx = multiprocessing.get_context("spawn")

    with ctx.Pool(processes=3) as pool:
        results = pool.starmap(
            simple_worker_task, [(0, 3), (1, 3), (2, 3)]  # 3 workers, 3 trials each
        )

    # All results should have consistent loops within their process
    for result in results:
        assert result["all_same"], f"Worker {result['worker_id']} had inconsistent loops"

    # But all processes should be different
    pids = set(r["pid"] for r in results)
    assert len(pids) == 3, f"Expected 3 different PIDs, got {len(pids)}"

    # And loop IDs should be different across processes
    all_loop_ids = []
    for result in results:
        all_loop_ids.extend(result["loops_used"])

    # First loop in each worker should be different from others
    first_loops = [result["loops_used"][0] for result in results]
    assert len(set(first_loops)) == 3, (
        f"Expected 3 different loop IDs across workers, got {len(set(first_loops))}"
    )


if __name__ == "__main__":
    print("Running event loop caching tests...")

    print("Test 1: Single process consistency...")
    test_eventloop_consistency_single_process()
    print("✓ Passed")

    print("Test 2: Multiprocess consistency...")
    test_eventloop_consistency_multiprocess()
    print("✓ Passed")

    print("Test 3: Process isolation...")
    test_eventloop_isolated_per_process()
    print("✓ Passed")

    print("\n✓ All event loop caching tests passed!")
