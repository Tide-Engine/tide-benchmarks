# ECS CPU comparison

Single-thread ECS ticks, including deferred churn changes; fixed frozen membership. Setup, digest, hashing, snapshots, rollback, networking and rendering excluded.

Median of process medians; range is process-median min/max. Each implementation occupies every launch position once per four rounds.

96 accepted processes; 4 rounds; 200 warmup and 400 measured ticks per process.

Milliseconds per tick; lower is faster. Parentheses show process-median ranges.

| Workload | Tide | Bevy | Flecs | EnTT |
| --- | ---: | ---: | ---: | ---: |
| particles-1m | 0.446475 (0.435450–0.578700) | 1.155625 (1.148350–1.265800) | 1.667100 (1.664550–1.734150) | 1.883975 (1.843650–1.912850) |
| wide-1m | 1.291375 (1.228250–1.344300) | 2.408375 (2.380050–2.603950) | 2.259550 (2.242800–2.287300) | 2.853600 (2.825750–2.880200) |
| filtered50-1m | 0.445225 (0.429050–0.462950) | 1.143575 (1.105900–1.201000) | 1.103475 (1.094950–1.123150) | 1.465600 (1.436350–1.468950) |
| filtered95-1m | 0.029250 (0.028900–0.029300) | 0.101200 (0.100000–0.106900) | 0.109625 (0.109100–0.112050) | 0.131950 (0.130050–0.137200) |
| filtered99-1m | 0.005750 (0.005700–0.005800) | 0.020225 (0.020100–0.020600) | 0.021875 (0.021650–0.022500) | 0.029025 (0.026700–0.029700) |
| churn-2k | 0.346950 (0.335550–0.389100) | 0.520375 (0.465500–0.686100) | 0.568750 (0.454200–0.739500) | 0.262675 (0.259800–0.270450) |

All accepted logical digests agree across implementations and rounds. These digests do not establish equal entity IDs, row order, serialization, or cross-platform determinism for the other libraries.

Tide and Bevy use their scheduled tick. Flecs uses its systems/pipeline; EnTT uses explicit tick dispatch and owning groups. See the source and methodology for these differences. No aggregate engine ranking is computed.

Excluded contended attempts: 1. Raw output and launch metadata remain in each case directory.
