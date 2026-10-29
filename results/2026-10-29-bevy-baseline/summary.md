Eleven separately validated workload batches; sources and binaries identical throughout.

Verified 66 processes in 3 alternating rounds.

ECS ticks only; excludes setup, snapshots, per-tick hashing, networking and rendering.

Times are milliseconds per tick, median of process medians. Ranges are process-median min/max.
Bevy/Tide is the median paired ratio; values above 1 favor Tide.

| Case | Threads | Tide ms (range) | Bevy ms (range) | C ms | Bevy/Tide |
| --- | ---: | ---: | ---: | ---: | ---: |
| particles-1m-1 | 1 | 0.458300 (0.447300–0.480300) | 1.152100 (1.150600–1.173750) | 0.413300 | 2.511× |
| particles-1m-4 | 4 | 0.126500 (0.124800–0.127400) | 0.430150 (0.429650–0.435650) | 0.124700 | 3.400× |
| wide-1m-1 | 1 | 1.332800 (1.325350–1.403500) | 2.496400 (2.386150–2.597150) | 1.017000 | 1.800× |
| wide-1m-4 | 4 | 0.671650 (0.671500–0.821200) | 1.177350 (1.143650–1.191000) | 0.555450 | 1.703× |
| filtered-1m-1 | 1 | 0.436050 (0.416050–0.480600) | 1.135850 (1.083500–1.144650) | 1.188250 | 2.604× |
| filtered-1m-4 | 4 | 0.410650 (0.404150–0.419800) | 0.411500 (0.411150–0.413650) | 0.625850 | 1.007× |
| filtered-frozen95-1m-1 | 1 | 0.029400 (0.029200–0.029400) | 0.100500 (0.100250–0.101100) | 1.071350 | 3.418× |
| filtered-frozen99-1m-1 | 1 | 0.005700 (0.005700–0.005800) | 0.019950 (0.019900–0.020000) | 1.083250 | 3.491× |
| filtered-frozen99-1m-4 | 4 | 0.005700 (0.005700–0.005800) | 0.022100 (0.021300–0.023300) | 0.710300 | 3.810× |
| churn-2k-1 | 1 | 0.338500 (0.337250–0.340300) | 0.320200 (0.296800–0.351500) | 0.200600 | 0.949× |
| churn-2k-4 | 4 | 0.350250 (0.331200–0.365500) | 0.304550 (0.263050–0.518250) | 0.200700 | 0.920× |
