# Flecs and EnTT comparator implementation

The standalone C++20 executables port the same particle, twelve-float motion,
and bullet-churn work as Tide's `bench/versus` and the Rust comparator. The
header `cpp/common.hpp` defines the common CLI, strictly ordered numeric work,
seed hash, logical-field digest, monotonic timing, and JSON output. Native
Tide/C and Bevy provide independent implementations of that work.

## Build and dependency contract

Flecs 4.1.6 is pinned to `fb55f3c25660425cfe1bc4cf5e6bff8b3f18a9b8`;
EnTT 4.0.0 is pinned to `85c6bba014049b5de8fad49d25424df2f1f6a8c1`.
Sources come from `.deps/flecs` and `.deps/entt`, fetched by `scripts/build.py`.
Flecs is compiled from its unmodified C17 amalgamation with its ordinary addons.
EnTT uses its unmodified headers and the platform C++ standard library.

The standalone CMake profile requires Clang and appends `-O2 -fno-fast-math
-ffp-contract=off` after configuration defaults, on the comparator executables
and the Flecs C library. On x86-64 it also pins `-march=x86-64 -mno-fma`.
`NDEBUG` is defined. The wrapper sources use `-Wall -Wextra -Wpedantic -Werror`;
third-party headers are system includes. On Windows `llvm-rc` is found beside
the selected C compiler; Flecs links the standard `ws2_32` and `dbghelp` libraries.

The equivalent direct local build command is:

```powershell
$env:TIDE_HIDDEN = '1'
cmake -S . -B build/cpp -G Ninja -DCMAKE_BUILD_TYPE=Release `
  '-DCMAKE_C_COMPILER=C:/Program Files/LLVM/bin/clang.exe' `
  '-DCMAKE_CXX_COMPILER=C:/Program Files/LLVM/bin/clang++.exe'
cmake --build build/cpp --parallel 4
```

Binaries are `build/cpp/bin/flecs-bench` and `entt-bench` (`.exe` on Windows).
Both accept the Bevy workload arguments and explicitly reject `--threads`
values other than 1. This version supplies a single-thread comparison; no
parallel scaling claim follows from these binaries.

## Flecs

Each tick calls `ecs_progress(world, dt)` through the default pipeline. Numeric
systems use fully cached queries and the C iterator callback, giving each
callback a component array to loop over. Frozen is an ordinary empty tag,
so `Motion, !Frozen` selects whole active tables. Query/scheduler tracking and
the end-of-frame structural merge remain in the timed tick.

Update is registered before Spawn in the same `EcsOnUpdate` phase, before any
entity deletion. Flecs documents same-phase entity-ID order; the wrapper also
checks the Spawn system's ID is greater than Update's. Spawn declares its
component output with a zero-source term. The first particle/wide tick
therefore spawns only; their later Spawn callbacks return immediately. During
churn, Fly processes existing bullets and queues deletions, then Fire queues
new bullets. Normal Flecs deferred creation/deletion application completes
before `ecs_progress` returns. New bullets do not move until the next tick.

Flecs's Fly/Fire registration order differs from Tide/Bevy's Fire/Fly order to
preserve the same visibility of newly created entities with the normal Flecs
pipeline. Component values, alive counts and frozen membership match. Cross-
engine entity IDs, command application order and iteration order are not part
of this benchmark's equivalence claim. The row loops do not bypass Flecs
storage, use raw external arrays as simulation state, or time manual calls to
the numeric kernel alone.

Flecs's bulk APIs were assessed before timing. `ecs_bulk_init` takes component
arrays, but the pinned implementation asserts that the supplied object is the
real world and that the world is not readonly (`src/entity.c`, lines 1401–1402),
so it cannot replace Fire's ordinary deferred operations. `ecs_bulk_new_w_id`
does support deferral, but accepts no per-entity data; its deferred path allocates
an ID array, creates each ID individually and adds the component individually
at merge, after which the distinct values still require sets. The comparator
therefore retains normal queued `ecs_new`/`ecs_set_id`, rather than adding that
extra bulk component-add pass. An immediate system with `ecs_bulk_init` is not
measured here.

Official sources consulted:

- [Pinned Flecs systems guide](https://github.com/SanderMertens/flecs/blob/fb55f3c25660425cfe1bc4cf5e6bff8b3f18a9b8/docs/Systems.md)
- [Pinned sync-point example](https://github.com/SanderMertens/flecs/blob/fb55f3c25660425cfe1bc4cf5e6bff8b3f18a9b8/examples/c/systems/sync_point/src/main.c)

## EnTT

Particles, unfiltered motion and bullets use ordinary component views. Filtered
motion uses a full-owning group for `Motion`, excluding `Frozen`, formed before
setup. This lets EnTT keep matching components together instead of forcing a
per-row sparse exclusion lookup. The timed update traverses the maintained
group; it does not build or refresh a hand-written active-row list per tick.

EnTT is a storage/query library that leaves scheduling to its caller. Its
wrapper explicitly dispatches the tick; it has no equivalent built-in pipeline
charge. Churn keeps reusable spawn and deletion vectors: it calculates spawn
values, traverses and updates old bullets, then applies births and deaths.
The vectors' filling and structural application are inside timing. This
retains deferred visibility while using ordinary registry range creation,
range insertion from component values, and range destruction. Reusable output
IDs are sized from the configured rate before timing. Setup, final digest, world construction and
destruction remain outside measurement for every implementation.

- [EnTT ECS guide, views/groups and scheduling model](https://github.com/skypjack/entt/wiki/Entity-Component-System)
- [Pinned registry API](https://github.com/skypjack/entt/blob/85c6bba014049b5de8fad49d25424df2f1f6a8c1/src/entt/entity/registry.hpp)

## Correctness checked during implementation

Windows x64 / Clang 23.1.2 builds pass warning-free. Before performance runs,
78 C++/Bevy comparisons passed (39 cases for each comparator), checking logical
digests and entity/frozen/moving counts. Cases cover particles at 1/17/10,000;
wide at 0/17; 10,000 wide with 0/50/95/99/100 percent frozen; churn rates
1/31/100; and warmup/measured counts of 1/1, 2/20 and 200/40. The last churn
case passes initial allocation and the maximum bullet lifetime into steady
state. All process exits succeeded and stderr was empty. Four-thread requests
are rejected with a clear diagnostic. These implementation-check timings are
discarded; publication uses the repository's separate controlled runner and
independent Tide/C/WASI validation.

The digest is a commutative sum of per-item FNV-1a/SplitMix64 hashes over
explicit little-endian logical fields. It checks exact float bits without
native padding, but does not establish entity-ID equivalence, serialized-world
equivalence, or general cross-platform determinism of Flecs or EnTT. Only
native Windows execution of these wrappers has been checked locally.
