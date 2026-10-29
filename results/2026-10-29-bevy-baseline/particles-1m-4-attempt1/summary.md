Verified 6 processes in 3 alternating rounds.

ECS ticks only; excludes setup, snapshots, per-tick hashing, networking and rendering.

Times are milliseconds per tick, median of process medians. Ranges are process-median min/max.
Bevy/Tide is the median paired ratio; values above 1 favor Tide.

| Case | Threads | Tide ms (range) | Bevy ms (range) | C ms | Bevy/Tide |
| --- | ---: | ---: | ---: | ---: | ---: |
| particles-1m-4 | 4 | 0.126500 (0.124800–0.127400) | 0.430150 (0.429650–0.435650) | 0.124700 | 3.400× |
