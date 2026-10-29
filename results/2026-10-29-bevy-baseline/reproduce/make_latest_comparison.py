import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
out = root / 'build/bevy-latest-fe5e96be1-cases'
accepted = json.loads((out / 'accepted.json').read_text(encoding='utf-8-sig'))
assert len(accepted) == 11, 'Expected all eleven preselected workloads'
summaries = [json.loads((root / p / 'summary.json').read_text(encoding='utf-8')) for p in accepted]
metas = [json.loads((root / p / 'metadata.json').read_text(encoding='utf-8-sig')) for p in accepted]
meta = metas[0]
assert all(s['valid'] and s['rounds'] == 3 and s['warmup'] == 200 and s['ticks'] == 400 and len(s['cases']) == 1 for s in summaries)
assert all(m['complete'] and m['revision'] == meta['revision'] and m['binaries'] == meta['binaries'] and m['files'] == meta['files'] and not m['git_status'] for m in metas)
summary = {**summaries[0], 'processes': sum(s['processes'] for s in summaries), 'cases': [s['cases'][0] for s in summaries], 'batches': accepted}
digests = {}
for c in summary['cases']:
    key = (c['workload'], c['count'], c['rate'], c['tagged'], c['frozen'])
    assert key not in digests or digests[key] == c['digest'], 'Cross-thread digest mismatch'
    digests[key] = c['digest']
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
import importlib.util
import sys
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('analyze', root / 'bench/bevy/analyze.py')
analyze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze)
(out / 'summary.md').write_text('Eleven separately validated workload batches; sources and binaries identical throughout.\n\n' + analyze.markdown(summary), encoding='utf-8')
def sha(path):
    return hashlib.sha256((root / path).read_bytes()).hexdigest()
original = (root / 'bench/bevy/src/main.rs').read_text()
table = (root / 'build/bevy-table-src/src/main.rs').read_text()
assert original.count('#[component(storage = "SparseSet")]') == 1
assert table == original.replace('#[component(storage = "SparseSet")]', '')
files = ['build/bevy-table-src/src/main.rs', 'build/bevy-table-src/Cargo.toml',
         'build/bevy-table-src/Cargo.lock', 'bench/versus/CMakeLists.txt',
         'build/bevy-table/release/tide-bevy-bench.exe', 'build/bevy-latest-validation.json']
for name in ('particles', 'wide', 'churn'):
    target = 'wide_lasting' if name == 'wide' else name
    for stage, source, ext in [('bevy-latest-moving', 'release', 'exe'),
                                ('bevy-latest-moving-web', 'web-release', 'wasm')]:
        source_path = f'build/{source}/bin/versus_{target}.{ext}'
        staged_path = f'build/{stage}/bin/versus_{name}.{ext}'
        assert sha(source_path) == sha(staged_path)
        files += [source_path, staged_path]
    generated = root / f'build/release/bench/versus/tide/versus_{target}'
    for path in sorted(generated.glob('*')):
        if path.suffix in ('.c', '.h'):
            relative = str(path.relative_to(root)).replace('\\', '/')
            staged = f'build/bevy-latest-moving/bench/versus/tide/versus_{name}/{path.name}'
            assert sha(relative) == sha(staged)
            files += [relative, staged]
provenance = {
    'revision': meta['revision'], 'working_tree_clean_at_measurement': not meta['git_status'],
    'tide_wide_target': 'versus_wide_lasting (LASTING / WIDE_LASTING; ordinary moving tag)',
    'bevy_storage': 'Table; only Frozen SparseSet annotation removed from comparator source',
    'staged_binaries_and_generated_source_verified': True,
    'native_ctests_passed': 6, 'wasi_ctests_passed': 6, 'cross_engine_checks_passed': 78,
    'prior_attempts_excluded': ['../bevy-latest-fe5e96be1', '../bevy-latest-fe5e96be1-retry'],
    'accepted_batches': accepted,
    'quiet_resets': sum(len(m.get('quiet_resets', [])) for m in metas),
    'sha256': {p: sha(p) for p in files},
}
(out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
shutil.copyfile(root / 'build/bevy-latest-validation.json', out / 'validation.json')
shutil.copyfile(root / 'build/bevy-table-src/src/main.rs', out / 'bevy-table-main.rs')

def label(c):
    if c['workload'] == 'particles':
        n = {10000:'10k',100000:'100k',1000000:'1M'}[c['count']]
        return f'{n} particles'
    if c['workload'] == 'churn':
        return '2,000 bullets spawned/tick'
    return '1M wide components' + (f", {c['frozen']}% frozen" if c['tagged'] else ', all active')
for case in summary['cases']:
    case['label'] = label(case)
data = json.dumps(summary['cases'])
html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;color:var(--foreground);font-family:var(--font-sans);font-size:14px;line-height:1.5}*{box-sizing:border-box}
.muted{color:var(--muted-foreground)}label{display:block;font-size:12px;margin-bottom:5px}select{width:100%;padding:11px;background:var(--card);color:var(--foreground);border:1px solid var(--border);border-radius:var(--radius);font:inherit}
.scope{font-size:12px;margin:10px 0 18px}.head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin:18px 0 12px}.result{font-size:22px;font-weight:650}.legend{font-size:12px}.chart{height:144px;display:flex;flex-direction:column;justify-content:space-around}.barrow{display:grid;grid-template-columns:90px 1fr;gap:8px;align-items:center}.track{height:36px;position:relative}.bar{height:36px;min-width:2px;border-radius:4px;background:var(--chart-1);transition:width .2s}.bevy{background:var(--chart-2)}.number{position:absolute;left:10px;top:7px;font-variant-numeric:tabular-nums;font-weight:600;color:var(--foreground);background:var(--card);padding:0 5px;border-radius:3px}
table{width:100%;border-collapse:collapse;margin-top:12px;font-size:12px;font-variant-numeric:tabular-nums}th,td{padding:8px 3px;border-bottom:1px solid var(--border);text-align:right}th:first-child,td:first-child{text-align:left}th{font-weight:500;color:var(--muted-foreground)}.foot{font-size:12px;color:var(--muted-foreground);margin-top:14px}
@media(max-width:420px){.head{display:block}.result{font-size:20px}.barrow{grid-template-columns:70px 1fr}.legend{margin-top:4px}}
</style></head><body>
<label for="workload" class="muted">Workload</label><select id="workload"></select>
<div class="scope muted">Latest dev fe5e96be1 · Bevy ECS 0.20.0 · Windows / Ryzen 9 7900X<br>Scheduled ECS tick, milliseconds · Lower is faster</div>
<div class="head"><div class="result" id="result"></div><div class="legend muted">Moving tags / Bevy Table</div></div>
<div class="chart" role="img" id="chart"><div class="barrow"><span>Tide</span><div class="track"><div class="bar" id="tidebar"></div><span class="number" id="tidenum"></span></div></div><div class="barrow"><span>Bevy</span><div class="track"><div class="bar bevy" id="bevybar"></div><span class="number" id="bevynum"></span></div></div></div>
<table><thead><tr><th>Engine</th><th>Median ms</th><th>Process range ms</th></tr></thead><tbody id="values"></tbody></table>
<div class="foot">3 alternating process pairs per workload; 200 warmup + 400 measured ticks each. Times are medians of process medians; speed ratio is the median paired ratio.<br>Excludes setup, hashing, snapshots, rollback, networking and rendering. Frozen membership stays fixed. 66 valid processes in 11 workload batches; all logical digests agree. Interrupted batches are excluded.</div>
<script>const cases=DATA;const select=document.getElementById('workload');cases.forEach((c,i)=>{const o=document.createElement('option');o.value=i;o.textContent=c.label+' — '+c.threads+' thread'+(c.threads===1?'':'s');select.appendChild(o)});select.value=cases.findIndex(c=>c.id==='filtered-frozen95-1m-1');function draw(){const c=cases[+select.value],max=Math.max(c.tide_ms,c.bevy_ms),ratio=c.ratio_bevy_over_tide;document.getElementById('result').textContent=ratio>=1?'Tide '+ratio.toFixed(2)+'× faster':'Bevy '+(1/ratio).toFixed(2)+'× faster';['tide','bevy'].forEach(e=>{document.getElementById(e+'bar').style.width=(100*c[e+'_ms']/max)+'%';document.getElementById(e+'num').textContent=c[e+'_ms'].toFixed(5)+' ms'});document.getElementById('values').innerHTML=['tide','bevy'].map(e=>'<tr><td>'+({tide:'Tide',bevy:'Bevy Table'}[e])+'</td><td>'+c[e+'_ms'].toFixed(5)+'</td><td>'+c[e+'_range_ms'].map(x=>x.toFixed(5)).join('–')+'</td></tr>').join('');document.getElementById('chart').setAttribute('aria-label',c.label+': Tide '+c.tide_ms+' milliseconds, Bevy '+c.bevy_ms+' milliseconds')};select.addEventListener('change',draw);draw();</script></body></html>'''.replace('DATA', data)
html = html.replace("ratio>=1?'Tide '", "Math.abs(ratio-1)<0.05?'Similar timing (within 5%)':ratio>=1?'Tide '")
html = html.replace("document.getElementById('chart').setAttribute", "if(c.tide_range_ms[0]<=c.bevy_range_ms[1]&&c.bevy_range_ms[0]<=c.tide_range_ms[1]){document.getElementById('result').textContent+=' · ranges overlap'};document.getElementById('chart').setAttribute")
(out / 'comparison.html').write_text(html, encoding='utf-8')
readme = f'''# Latest dev vs Bevy — fresh local run

Measured revision: `{meta['revision']}`. The checkout fast-forwarded to origin/dev; no tracked source changed. No hash pins changed.

Tide uses current moving tags: target `versus_wide_lasting`, compiled with `LASTING` and `WIDE_LASTING`, staged as `versus_wide.exe` for the existing runner. The ordinary `versus_wide` target explicitly retains `[Sparse]` and is not the timed wide variant. Matching generated sources and original/staged binary identities are verified in provenance.json.

Bevy ECS 0.20.0 uses Table storage for Frozen; its copied source differs only by removing the SparseSet annotation. The exact source is bevy-table-main.rs. Rust 1.95.0, O2, no LTO, baseline x86-64, FMA disabled. Tide Clang 23.1.2, normal release O2 with strict floating-point flags. Hardware: Windows / Ryzen 9 7900X.

Run: `build/run-latest-cases.ps1`, using `bench/bevy/run.ps1` once per case with `-Rounds 3 -FilterSweep -OnlyCases <id> -BuildDir build/bevy-latest-moving -BevyExe build/bevy-table/release/tide-bevy-bench.exe`; each batch is validated separately with `bench/bevy/analyze.py`. `build/make_latest_comparison.py` verifies identical inputs and cross-thread digests and assembles this report. The eleven workload IDs were selected before these batches started, focusing on 1M particles, dense wide, 50/95/99% frozen and churn, with available 1/4-thread variants. This is a subset of the original sixteen-case suite.

66 processes, 11 separately validated case batches, 3 alternating pairs each, 200 warmup and 400 measured ticks per process. Shared benchmark mutex, 15-second quiet guard before each batch, 250 ms nominal contention polling. No detected contention in accepted processes. Source/configuration/binary hashes are identical across accepted batches. Desktop activity, clocks, affinity and temperature are uncontrolled. Medians and min/max ranges are process statistics; ratios are paired, not ratios of displayed aggregate medians. Individual batch metadata retains quiet resets and launch times.

Two full-suite attempts in ../bevy-latest-fe5e96be1 and ../bevy-latest-fe5e96be1-retry are excluded in full: other sessions' cmake/ninja builds overlapped timed processes and the runner stopped. The second failed in round 1. Raw records and failed analyses are retained there. Any rejected per-workload attempts also remain alongside accepted ones; accepted.json explicitly lists which complete batches entered this report. Selection depends on completeness/correctness/contention, never timing values.

Validation: 6 native and 6 WASI target tests pass; 78 native/C/WASI/Bevy logical comparisons pass. Every timed pair and cross-thread workload matches its logical digest. Digests are unordered logical-value checks, not full world/ID/serialization equivalence or a Bevy cross-platform determinism guarantee.

Scope is scheduled ECS ticks, including churn structural work. Excludes setup, final digest, per-tick world hashing, snapshots, rollback, networking and rendering. Frozen membership does not change during measurement. These are not whole-game FPS or client-performance results. No browser/GPU tests were needed for this CPU-only refresh.

Full numbers: summary.md; raw records: each accepted batch's records.jsonl; interactive chart: comparison.html.
'''
(out / 'README.md').write_text(readme, encoding='utf-8')
print(json.dumps({'report': str(out), 'revision': meta['revision'], 'cases': len(summary['cases']), 'processes': summary['processes']}))
