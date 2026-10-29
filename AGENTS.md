# Benchmark maintenance

Keep comparisons auditable and reproducible. Pin every dependency revision and compiler setting. Preserve logical work, float operation order, deferred entity changes, and digest contracts across implementations. Never publish failed, contended or incomplete timing batches as valid results. Keep adverse outcomes and explain scope and implementation differences.

Set `TIDE_HIDDEN=1` before shell commands. Run bounded CPU benchmarks only. Coordinate performance runs under the shared `Local\TideClaudeContinuationBenchmark` mutex on Windows; do not build or test while another agent measures. Do not run binaries from pre-existing engine checkouts; build the pinned engine dependency locally.

Source belongs here; Tide Engine remains an external pinned dependency. Do not change the engine for a comparison. Use native release `-O2`, strict IEEE arithmetic, no fast math or FMA contraction, baseline x86-64 on x86-64. Record exceptions rather than silently changing flags.

Commit source, methodology and evidence together after correctness validation. Work on `dev`; do not create pull requests or manually dispatch workflows unless asked. The root agent coordinates commits and pushes.
