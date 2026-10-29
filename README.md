# Tide ECS benchmarks

Reproducible CPU workloads for [Tide](https://github.com/Tide-Engine/tide-engine),
[Bevy ECS](https://github.com/bevyengine/bevy),
[Flecs](https://github.com/SanderMertens/flecs) and
[EnTT](https://github.com/skypjack/entt). Maintained by the Tide project. Contributions
that improve an implementation while preserving the workload are welcome.

The suite measures ECS updates and the structural work that completes a tick.
It checks matching logical results before comparing time. It does **not** measure
whole-engine FPS, rendering, networking, rollback, retained snapshots or per-tick
world hashing. Frozen membership is fixed during these measurements.

## Run it

Prerequisites: Python 3.10+, Git, CMake 3.25+, Ninja, Clang with a C++20 standard
library/toolchain, and Rust 1.95.0. On Windows, install the Visual Studio C++ build
tools and Windows SDK as well as LLVM. On Linux, Tide's platform build needs X11
development headers. A web correctness check also needs Node 24.22.1 or newer 24.x.
The scripts download the exact dependency commits in [dependencies.json](dependencies.json).
They build these dependencies locally; no installed Tide package is used.

```sh
git clone https://github.com/Tide-Engine/tide-benchmarks.git
cd tide-benchmarks
rustup toolchain install 1.95.0 --profile minimal
python scripts/build.py --web
python scripts/validate.py --output build/validation.json --web
python scripts/run.py --output results/my-machine
python scripts/analyze.py results/my-machine
```

See each script's `--help` for options. Omit `--web` from both build and validation
for a native-only run. `LLVM_ROOT` can point to a standalone LLVM installation.
The scripts set `TIDE_HIDDEN=1` for their own child processes. No visible game
windows or audio devices are needed.

Run correctness checks and finish other builds before timing. The runner keeps
raw stdout/stderr and rejects failed, incomplete, logically different or detected
contended attempts. An uncontended run still has ordinary desktop, placement,
clock and thermal variation; publish its ranges and machine identity.

## What is compared

| Workload | Work per tick |
| --- | --- |
| Particles | One million four-float particles fall and bounce against bounds |
| Wide components | One million twelve-float bodies update velocity and position |
| Frozen bodies | The same bodies, with 50%, 95% or 99% selected by a seeded tag and skipped |
| Churn | Spawn 2,000 bullets, update existing bullets, remove expired bullets; new bullets first move next tick |

The common comparison offers **one thread to every implementation**. A separate
Tide/Bevy report offers one and four threads; no parallel capability is inferred
for an unmeasured implementation. Each implementation uses its own storage and
iteration facilities. This is a comparison of concrete implementations, not a
claim that their feature sets or services are identical.

| Implementation | Measured path |
| --- | --- |
| Tide | Generated scheduled systems; moving Frozen tags place entities in separate archetypes |
| Bevy ECS | Single-thread schedule with normal query/change detection; Frozen uses Table storage |
| Flecs | Cached archetype systems through its pipeline |
| EnTT | Owning-group iteration and explicit tick dispatch; EnTT does not supply the same schedule as the other paths |

All use the same initial values, 60 Hz step, basic floating-point operation order,
lifetimes and deferred-spawn behavior. Native C/C++ builds use O2, no fast math and
no FMA contraction; the Rust build uses O2 and disables FMA on baseline x86-64.
No engine is required to have the same component layout or entity IDs. Logical
digests are order-independent component-value checks; they are not a proof of
identical worlds, serialization or cross-platform determinism in other engines.

Initialization and the final digest are outside timing. The first particle/wide
warmup tick spawns without updating. Churn warms up for 200 ticks, beyond the
longest bullet lifetime. Official runs then measure 400 ticks per process in four
rounds. Engine order rotates so each implementation occupies every launch position
once. Each workload is a separate complete batch; input hashes must remain fixed.
Reports show medians of process medians and their min/max ranges, with no composite
score across workloads. Implementation details: [C++ paths](notes/cpp.md),
[runner and validation](notes/runner.md).

## Evidence

- [Tide / Bevy baseline, October 29, 2026](results/2026-10-29-bevy-baseline/README.md):
  eleven workloads and thread budgets, three alternating pairs each, with raw
  output and both excluded full-suite attempts preserved. This earlier run used
  the engine repository's original harness; its scope and estimator are separate.
- New four-engine measurements are recorded alongside their build and validation
  identities under `results/`; each report names the exact revisions it measured.

Numbers describe the listed hardware, versions, workload and implementation.
Include ties and losses when presenting them. The tests cover selected CPU paths;
they do not establish an engine's maximum throughput or predict a particular game.

## Scope and contributions

The benchmark repository owns the comparison programs, scripts and evidence.
Tide remains an external pinned dependency, including its existing Tide/C
workloads. The engine website consumes a compact presentation of a dated report
and links back here. Updating a dependency creates a new report; historical raw
results remain unchanged.

For improvements, keep arithmetic and timing boundaries equivalent, describe the
chosen API, run validation, and retain both the old and new results. Additional
workloads can measure tag mutation, snapshots and hashing separately. Comparing
different engines' networking features would require its own stated workload.

Benchmark code is licensed **MIT OR Apache-2.0**, inherited from Tide where copied.
External projects retain their own licenses; their pinned checkouts include those
licenses. Dependency sources are fetched into ignored `.deps/`, not vendored here.
