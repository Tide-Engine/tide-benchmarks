# Comparison runner and evidence contracts

`scripts/run.py` runs the six fixed serial workloads in independently accepted case batches. The four engines are Tide, Bevy, Flecs and EnTT. Four cyclic rounds put every engine in every launch position once; an optional round count must be a multiple of four. Official results use 200 warmup and 400 measured ticks per process. Setup and final logical digests remain outside timing, and churn includes deferred structural changes.

The build manifest is schema 1 with `engines: {Tide: {particles, wide, churn}, Bevy: {executable}, Flecs: {executable}, EnTT: {executable}}`, `files: {path: sha256}`, and free-form build `metadata`. Paths are absolute or relative to this repository root. Tide's wide binary is the moving-tag target, not its explicitly sparse target. Optional `web: {node, runner, particles, wide, churn}` enables correctness checks against Tide WASI. The runner pins the manifest bytes, its own three implementation scripts and every executable, in addition to all manifest input pins. It checks every input before and after a case and at suite end.

Each case holds the shared `Local\TideClaudeContinuationBenchmark` Windows mutex or a per-user POSIX `flock` in the temporary directory. It waits for 15 continuously quiet seconds before measurement, restarts that wait if known work appears before a process, and inventories processes at nominal 250 ms intervals during a process. Windows uses native Toolhelp process names; POSIX uses `ps` process names. The guard detects known compiler/build tools and native Tide/Flecs/EnTT/Bevy test or benchmark executable names. Arbitrary Node tasks, browsers, desktop activity, CPU affinity, clock and thermal variation remain uncontrolled. This guard is not identical to the historical PowerShell runner's additional Node command-line checks. Very short processes may finish between inventory polls.

Only contention retries automatically, at most three complete attempts per case. Every failed attempt retains its metadata and raw records, and valid cases list their accepted attempt explicitly in `suite.json`. Incomplete, failed, changed-input, nonzero-stderr and mismatching-digest runs cannot contribute a result. Timing values never influence attempt selection. A quiet timeout or correctness failure stops the suite rather than being silently retried.

`scripts/analyze.py` validates the stored manifest, all accepted case identities, balanced process order, expected arguments, start/end file hashes, raw stdout/stderr hashes, parsed result equality, success and contention flags, process intervals, logical digests and population counts. Non-Tide statistics are recomputed from their tick samples. Tide's existing harness supplies rounded median/mean values and an independent C correctness check; it does not emit its individual samples. All engines' process medians are summarized without pooling ticks. Ranges are min/max process medians, not confidence intervals. Other-engine/Tide ratios pair the corresponding cyclic round; no global score is calculated. Tide's C reference is contextual and runs after Tide in the same process, not as a separately rotated contender.

`scripts/validate.py` runs 75 workload/phase combinations across all four native implementations plus Tide's C reference: small and empty wide sets, seeded populations, frozen densities including zero and all, and early/steady churn with three rates. Optional `--web` adds native/WASI comparisons. These timings are discarded. Matching unordered value digests and counts do not prove identical entity IDs, row order, serialized worlds or cross-platform determinism of the other libraries.

`python scripts/test_runner.py` exercises complete acceptance and negative cases for missing/extra processes, contention, failed/incomplete records, raw data tampering, false sample statistics, digest/options/count mismatches, modified commands and binaries, changed input pins, launch-order and interval violations, path traversal, stderr, NaNs, worker budgets, Tide/C failure, manifest tampering and omitted retry history. It launches no performance workload. All 26 tests pass on Windows/Python 3.14.4; native process enumeration also completed successfully. POSIX paths are implemented but were not executed in this Windows validation.

Usage:

```
python scripts/validate.py --output build/validation.json --web
python scripts/run.py --output results/<label>
python scripts/run.py --output results/<label> --only filtered95-1m churn-2k
python scripts/analyze.py results/<label>
```

Output directories/files must be new. The first publication uses the same pinned inputs in every accepted batch and retains excluded attempts; builds and validation finish before any timing run starts.
