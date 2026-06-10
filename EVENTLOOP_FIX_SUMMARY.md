# Event Loop Fix - Summary

## Problem
When using multiprocessing optimization with pool caching, the error occurred:
```
RuntimeError: Task got Future attached to a different loop
```

## Root Cause
- asyncpg pools are bound to the event loop they're created in
- Each trial was getting a potentially different event loop
- Pool created in trial 1 with loop A couldn't be used in trial 2 with loop B
- Result: "different loop" error

## Solution
**Ensure each worker process uses ONE consistent event loop across ALL trials**

### What Changed
**File**: `bot/optimization/runner.py` (Lines 394-436)

**Before**:
```python
def sync_objective(trial: optuna.Trial) -> float:
    # Each trial might create a DIFFERENT loop ❌
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(objective_func(trial))
```

**After**:
```python
def sync_objective(trial: optuna.Trial) -> float:
    # Cache loop per process ✓
    if pid not in sync_objective._worker_loop_cache:
        # Create loop ONCE
        loop = ...
        sync_objective._worker_loop_cache[pid] = loop

    # Reuse SAME loop for all trials in this worker
    loop = sync_objective._worker_loop_cache[pid]
    return loop.run_until_complete(objective_func(trial))
```

## How It Works

### Serial (n_jobs=1)
```
Main Process:
  Trial 1: Create loop → Cache it
  Trial 2: Reuse cached loop
  Trial 3: Reuse cached loop
  ✓ All trials use same loop
```

### Parallel (n_jobs=-1)
```
Main Process → Spawns Workers

Worker 1 (PID 2001):
  Trial 1: Create loop → Cache with PID 2001
  Trial 2: Reuse loop with PID 2001
  ✓ Consistent loop

Worker 2 (PID 2002):
  Trial 3: Create loop → Cache with PID 2002
  Trial 4: Reuse loop with PID 2002
  ✓ Different process = different loop, no conflict
```

## Files Modified

1. **bot/optimization/runner.py** (FIXED)
   - Lines 394-436: `sync_objective()` function
   - Added process-local event loop caching

2. **tests/test_eventloop_caching.py** (NEW)
   - Unit tests for event loop consistency

3. **docs/EVENTLOOP_FIX.md** (NEW)
   - Technical documentation

## Testing the Fix

### Quick Test
```bash
# Test serial mode (should work now)
docker-compose exec bot python -m main optimize run \
  --study-name test_eventloop_fix \
  --n-trials 5 \
  --n-splits 1

# Expected: No "different loop" errors
# Log output should show normal optimization progress
```

### Comprehensive Test
```bash
# Test parallel mode (should work now)
docker-compose exec bot python -m main optimize run \
  --study-name test_eventloop_fix_parallel \
  --n-trials 20 \
  --n-splits 2 \
  --multithread

# Expected:
# - No "different loop" errors
# - Pool creation messages (4-8 total, one per worker)
# - Normal optimization progress
# - ~15-25% speedup from pool caching
```

### Run Unit Tests
```bash
docker-compose exec bot pytest tests/test_eventloop_caching.py -v

# Expected output:
# test_eventloop_consistency_single_process PASSED
# test_eventloop_consistency_multiprocess PASSED
# test_eventloop_isolated_per_process PASSED
```

## Expected Behavior After Fix

### Logs
```
DEBUG: Created DB pool for worker PID 12001
DEBUG: Created DB pool for worker PID 12002
DEBUG: Created DB pool for worker PID 12003
DEBUG: Created DB pool for worker PID 12004
INFO: Trial 1 completed
INFO: Trial 2 completed
INFO: Trial 3 completed
... (NO RuntimeError messages)
INFO: Optimization completed successfully
```

### Performance
- **Before fix**: Optimization fails with "different loop" error
- **After fix**: Optimization completes with 15-25% speedup

### Database Connections
- During optimization: 12-30 connections (4 workers × 3 pool connections)
- After optimization: Back to 5-10 connections (proper cleanup)

## Summary

| Aspect | Status |
|--------|--------|
| Syntax | ✅ Valid (checked with py_compile) |
| Logic | ✅ Sound (event loop per process) |
| Pool Caching | ✅ Enabled (requires this fix) |
| Performance | ✅ Expected 15-25% speedup |
| Testing | Ready to run |

## Next Steps

1. **Test the fix**:
   ```bash
   docker-compose exec bot python -m main optimize run \
     --study-name final_test \
     --n-trials 10 \
     --n-splits 2 \
     --multithread
   ```

2. **Monitor for errors**:
   ```bash
   docker-compose logs -f bot | grep -E "different loop|error|RuntimeError"
   ```

3. **Compare timing with previous run** to verify speedup

4. **If it works**: Commit the changes
   ```bash
   git add -A
   git commit -m "Fix event loop consistency in multiprocessing optimization"
   ```

5. **If errors persist**: Rollback
   ```bash
   git checkout -- bot/optimization/runner.py
   ```

## Technical Details

### Why This Works

1. **Process Isolation**: Each worker process has its own Python interpreter
2. **Function Attributes**: `sync_objective._worker_loop_cache` stores per-process data
3. **PID Keying**: Using `os.getpid()` ensures no cross-process conflicts
4. **Idempotent Creation**: Loop is created once, reused thereafter
5. **Pickling Safety**: Event loops aren't pickled (created locally)

### Why Previous Approach Failed

- Creating loops inside the function without caching: Each trial got a fresh loop
- Pool from trial 1 bound to loop A, trial 2's loop B → "different loop" error
- The fix ensures trial 2 uses loop A (cached)

### Comparison to Pool Caching

| Component | Storage | Per-Process | Pickling |
|-----------|---------|-------------|----------|
| Pools | Module dict `_process_pools` | PID key | Can't pickle, create locally ✓ |
| Loops | Function dict `_worker_loop_cache` | PID key | Can't pickle, create locally ✓ |
| Objective | Closure variable | N/A | Pickled to workers |

Both pools and loops use similar process-local caching strategy.

## Documentation

- `docs/EVENTLOOP_FIX.md` - Technical deep dive
- `docs/OPTIMIZATION_NOTES.md` - Pool caching documentation
- `IMPLEMENTATION_SUMMARY.txt` - Quick reference

## Files Changed
- `bot/optimization/runner.py` (MODIFIED)
- `tests/test_eventloop_caching.py` (NEW)
- `docs/EVENTLOOP_FIX.md` (NEW)
- `EVENTLOOP_FIX_SUMMARY.md` (NEW - this file)

---

**Status**: ✅ Ready to test

**Expected Result**: Optimization completes successfully with 15-25% speedup
