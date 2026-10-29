Verified 6 processes in 3 alternating rounds.

ECS ticks only; excludes setup, snapshots, per-tick hashing, networking and rendering.

Times are milliseconds per tick, median of process medians. Ranges are process-median min/max.
Bevy/Tide is the median paired ratio; values above 1 favor Tide.

| Case | Threads | Tide ms (range) | Bevy ms (range) | C ms | Bevy/Tide |
| --- | ---: | ---: | ---: | ---: | ---: |
| filtered-frozen99-1m-4 | 4 | 0.005700 (0.005700–0.005800) | 0.022100 (0.021300–0.023300) | 0.710300 | 3.810× |
