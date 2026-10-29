# Initial public comparison

The owner requested a separate public benchmark repository so implementation,
dependencies, reproduction and raw evidence can be reviewed without adding more
comparison machinery to the engine repository. `Tide-Engine/tide-benchmarks`
owns those artifacts; the engine owns its website presentation and continues to
provide the pinned Tide/C workloads as an external dependency.

This first common suite uses Tide at fe5e96be1, Bevy ECS 0.20.0 with Table Frozen,
Flecs 4.1.6 with cached pipeline systems and EnTT 4.0.0 with owning filtered groups.
EnTT's explicit dispatch and Flecs' deferred creation contract are documented in
cpp.md. Six fixed serial workloads cover particles, dense and frozen wide data,
and churn. Existing one/four-thread Tide/Bevy evidence is archived separately,
including excluded attempts. No composite ranking or whole-engine FPS claim.

Local implementation validation: 75 workload/phase cases agree across Tide/C,
Bevy, Flecs and EnTT, plus Tide WASI. The comparator author also checked 78 C++
comparisons against Bevy, then repeated the nine affected churn checks after
using EnTT's bulk API. The runner's 26 evidence tests pass. Independent read-only
review checked workload equivalence, deferral, timing and rejection rules and
found two build-contract gaps: LLVM_ROOT precedence and Cargo environment
overrides. Both are fixed before final manifest generation and measurements.

Validation is on Windows/Ryzen 9 7900X with Clang 23.1.2, Rust 1.95.0, Python
3.14.4 and Node 24.22.1. The scripts provide POSIX paths, but those paths have not
been executed here. Only Tide receives WASI validation; Bevy/Flecs/EnTT results
in this publication are native CPU results. No browser rendering, networking,
cross-OS, mobile or sanitizer performance claim follows.

The public four-engine report is `results/2026-10-29-four-ecs`: 96 accepted
processes, four cyclic rounds, 200 warmup and 400 measured ticks each. One
50%-frozen attempt overlapped another build and was rejected in full; its
evidence remains, and three quiet resets are recorded across accepted cases.
Every measured digest agrees; the exact measured manifest also matches the
75-case validation report. No results from different reports are pooled.

On this machine Tide has the lowest median in particles, dense wide and each
fixed frozen-density case; EnTT leads churn. Churn varies substantially in Bevy
and Flecs, and the earlier separate Tide/Bevy report has different churn medians.
The website carries complete medians/ranges and implementation descriptions,
including EnTT's explicit dispatch and Flecs' ordinary deferred creation path.
These observations are specific to the pinned implementations and workloads.
