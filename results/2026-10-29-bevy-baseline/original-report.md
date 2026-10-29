# Latest dev vs Bevy — fresh local run

Measured revision: `fe5e96be1c61c7372590e7466dc26810a910bb14`. The checkout fast-forwarded to origin/dev; no tracked source changed. No hash pins changed.

Tide uses current moving tags: target `versus_wide_lasting`, compiled with `LASTING` and `WIDE_LASTING`, staged as `versus_wide.exe` for the existing runner. The ordinary `versus_wide` target explicitly retains `[Sparse]` and is not the timed wide variant. Matching generated sources and original/staged binary identities are verified in provenance.json.

Bevy ECS 0.20.0 uses Table storage for Frozen; its copied source differs only by removing the SparseSet annotation. The exact source is bevy-table-main.rs. Rust 1.95.0, O2, no LTO, baseline x86-64, FMA disabled. Tide Clang 23.1.2, normal release O2 with strict floating-point flags. Hardware: Windows / Ryzen 9 7900X.

Run: `build/run-latest-cases.ps1`, using `bench/bevy/run.ps1` once per case with `-Rounds 3 -FilterSweep -OnlyCases <id> -BuildDir build/bevy-latest-moving -BevyExe build/bevy-table/release/tide-bevy-bench.exe`; each batch is validated separately with `bench/bevy/analyze.py`. `build/make_latest_comparison.py` verifies identical inputs and cross-thread digests and assembles this report. The eleven workload IDs were selected before these batches started, focusing on 1M particles, dense wide, 50/95/99% frozen and churn, with available 1/4-thread variants. This is a subset of the original sixteen-case suite.

66 processes, 11 separately validated case batches, 3 alternating pairs each, 200 warmup and 400 measured ticks per process. Shared benchmark mutex, 15-second quiet guard before each batch, 250 ms nominal contention polling. No detected contention in accepted processes. Source/configuration/binary hashes are identical across accepted batches. Desktop activity, clocks, affinity and temperature are uncontrolled. Medians and min/max ranges are process statistics; ratios are paired, not ratios of displayed aggregate medians. Individual batch metadata retains quiet resets and launch times.

Two full-suite attempts in ../bevy-latest-fe5e96be1 and ../bevy-latest-fe5e96be1-retry are excluded in full: other sessions' cmake/ninja builds overlapped timed processes and the runner stopped. The second failed in round 1. Raw records and failed analyses are retained there. Any rejected per-workload attempts also remain alongside accepted ones; accepted.json explicitly lists which complete batches entered this report. Selection depends on completeness/correctness/contention, never timing values.

Validation: 6 native and 6 WASI target tests pass; 78 native/C/WASI/Bevy logical comparisons pass. Every timed pair and cross-thread workload matches its logical digest. Digests are unordered logical-value checks, not full world/ID/serialization equivalence or a Bevy cross-platform determinism guarantee.

Scope is scheduled ECS ticks, including churn structural work. Excludes setup, final digest, per-tick world hashing, snapshots, rollback, networking and rendering. Frozen membership does not change during measurement. These are not whole-game FPS or client-performance results. No browser/GPU tests were needed for this CPU-only refresh.

Full numbers: summary.md; raw records: each accepted batch's records.jsonl; interactive chart: comparison.html.
