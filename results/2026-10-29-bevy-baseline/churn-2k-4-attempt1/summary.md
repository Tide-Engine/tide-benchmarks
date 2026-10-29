Verified 6 processes in 3 alternating rounds.

ECS ticks only; excludes setup, snapshots, per-tick hashing, networking and rendering.

Times are milliseconds per tick, median of process medians. Ranges are process-median min/max.
Bevy/Tide is the median paired ratio; values above 1 favor Tide.

| Case | Threads | Tide ms (range) | Bevy ms (range) | C ms | Bevy/Tide |
| --- | ---: | ---: | ---: | ---: | ---: |
| churn-2k-4 | 4 | 0.350250 (0.331200–0.365500) | 0.304550 (0.263050–0.518250) | 0.200700 | 0.920× |
