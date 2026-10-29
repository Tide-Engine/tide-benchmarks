# Four-engine ECS comparison — October 29, 2026

[All timings and ranges](summary.md) · [Machine-readable results](summary.json) ·
[Build manifest](manifest.json) · [Correctness evidence](validation.json) ·
[Accepted/rejected attempt ledger](suite.json)

This common **single-thread** suite compares Tide, Bevy ECS, Flecs and EnTT on
Windows x86-64 / Ryzen 9 7900X. The benchmark implementation was committed before
timing; its exact revision is recorded in `manifest.json` under
`metadata.benchmark_revision`. Dependency pins:

- Tide `fe5e96be1c61c7372590e7466dc26810a910bb14`, moving Frozen tags.
- Bevy ECS 0.20.0 with Table Frozen, Rust 1.95.0.
- Flecs 4.1.6, `fb55f3c25660425cfe1bc4cf5e6bff8b3f18a9b8`.
- EnTT 4.0.0, `85c6bba014049b5de8fad49d25424df2f1f6a8c1`.

Clang 23.1.2 builds Tide and both C/C++ comparators with O2, strict floating-point
operations and no FMA contraction. Rust also uses O2 with baseline x86-64 and FMA
disabled. The exact sources, configurations, generated Tide code and executables
are hash-pinned in the manifest and each case's metadata. Their identities remain
the same throughout accepted measurements.

There are 96 accepted processes: six cases × four implementations × four rounds.
Each process warms up for 200 ticks and measures 400. Every implementation occupies
each launch position once per workload. Cases are separate batches, with the
shared benchmark mutex, a 15-second quiet guard and nominal 250 ms process-name
polling. Three quiet resets are recorded across accepted batches.

`filtered50-1m/attempt-1` overlapped another build and was excluded in full. The
runner retained its raw evidence and accepted the subsequent complete attempt.
No attempt was selected or rejected because of its timing. Arbitrary Node/browser
tasks, other desktop activity, placement, clocks and temperatures remain uncontrolled.

The main comparison measures ECS updates and deferred structural work. Setup,
digest computation, per-tick world hashing, snapshots, rollback, networking and
rendering are outside timing. Frozen membership remains fixed. The logical work
matches, while implementations provide different services: Tide and Bevy use
scheduled systems, Flecs uses its cached pipeline, and EnTT uses explicit dispatch
with owning groups. See [C++ implementation details](../../notes/cpp.md).

All accepted logical digests agree. Before timing, 75 small/edge/steady-state cases
matched across all four native implementations, Tide's independent C reference
and Tide WASI. `validation.json` pins the same build manifest as `suite.json`.
The runner's 26 negative/acceptance tests pass. Windows was exercised; other OS
paths and Bevy/Flecs/EnTT WebAssembly were not validated here.

Tide has the lowest sampled median for particles, dense wide components and the
three frozen densities. EnTT has the lowest churn median. Bevy and Flecs churn
ranges are wide. The earlier [Tide/Bevy report](../2026-10-29-bevy-baseline/README.md)
is kept separately; its different churn observations demonstrate why these numbers
should retain their ranges and should not be pooled into a universal ranking.

## Reproduce or verify

Follow the repository [build instructions](../../README.md), then:

```sh
python scripts/validate.py --output build/my-validation.json --web
python scripts/run.py --output results/my-machine
python scripts/analyze.py results/my-machine
```

To verify this committed evidence without rebuilding any implementation:

```sh
python scripts/analyze.py results/2026-10-29-four-ecs
```

Paths within recorded commands describe the measurement machine. The analyzer
uses saved relative raw-output paths and pinned identities; it does not require
that machine's original build directory. Ranges are process-median min/max values,
not confidence intervals. No global score or maximum-throughput claim is made.
