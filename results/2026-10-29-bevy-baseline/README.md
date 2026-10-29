# Tide / Bevy baseline, October 29, 2026

This is the unchanged evidence collected before the standalone repository was
created. [Full results and ranges](summary.md), [validation](validation.json),
[source/binary identities](provenance.json).

Tide revision: [`fe5e96be1c61c7372590e7466dc26810a910bb14`](https://github.com/Tide-Engine/tide-engine/tree/fe5e96be1c61c7372590e7466dc26810a910bb14).
Bevy ECS 0.20.0, Table storage; exact comparator source: [bevy-table-main.rs](bevy-table-main.rs).
Windows / Ryzen 9 7900X, Clang 23.1.2 O2 and Rust 1.95.0 O2, strict floats.
66 valid processes: eleven separately measured workloads/thread budgets with
three alternating Tide/Bevy pairs, 200 warmup and 400 measured ticks each.

The timing scope excludes setup, final digest, per-tick hashing, retained snapshots,
rollback, networking and rendering. Frozen membership remains fixed. Tide's wide
target is `versus_wide_lasting` (moving tags); Bevy's Frozen is Table storage.
All logical digests match, and 78 additional checks agree across native Tide/C,
Tide WASI and Bevy. Six selected CTests passed on native and on WASI.

The directory names in [accepted.json](accepted.json) are original engine-worktree
paths. Their final directory components are the case folders preserved here.
Each contains its raw outputs, metadata, records and summary. For example:

```sh
python results/2026-10-29-bevy-baseline/verify-original.py results/2026-10-29-bevy-baseline/particles-1m-1-attempt1
```

That original analyzer verifies record completeness, raw hashes, options, digests
and statistics without requiring the original executables. The two interrupted
full-suite attempts are under [excluded/](excluded/), entirely excluded from the
numbers. Their raw data and failed summaries remain intact.

[original-report.md](original-report.md) and [reproduce/](reproduce/) preserve the
original environment-specific instructions and helper scripts. Their absolute
paths refer to the measurement machine. The original engine runner and workloads
are available at the pinned Tide revision above. For a portable new measurement,
follow the standalone repository [instructions](../../README.md), which build the
same moving-tag Tide and Table-storage Bevy paths alongside Flecs and EnTT.

This historical batch uses three alternating pairs and a PowerShell process guard.
The new four-engine suite uses four cyclic rounds and a native process-name guard.
Reports remain separate and are never pooled. Four-thread 50%-frozen results are
effectively tied; churn is variable with overlapping ranges. The sampled workloads
are not a throughput ceiling for either implementation.
