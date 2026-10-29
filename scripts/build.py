"""Fetch exact dependency commits and build the reproducible CPU comparison."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, 'TIDE_HIDDEN': '1'}


def run(args, cwd=ROOT, capture=False):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=ENV,
                            text=True, capture_output=capture, check=True)
    return result.stdout.strip() if capture else None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compiler(name):
    explicit = os.environ.get('LLVM_ROOT')
    if explicit:
        path = Path(explicit) / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))
        if not path.is_file():
            raise RuntimeError(f'{name} is missing from LLVM_ROOT: {path}')
        return str(path)
    found = shutil.which(name)
    if found:
        return found
    for base in ('C:/Program Files/LLVM',):
        if base:
            path = Path(base) / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))
            if path.is_file():
                return str(path)
    raise RuntimeError(f'{name} not found; install LLVM and set LLVM_ROOT or PATH')


def fetch(name, pin):
    target = ROOT / '.deps' / name
    if not (target / '.git').exists():
        if target.exists() and any(target.iterdir()):
            raise RuntimeError(f'Refusing nonempty non-Git dependency directory: {target}')
        target.mkdir(parents=True, exist_ok=True)
        run(['git', 'init', str(target)])
        run(['git', 'remote', 'add', 'origin', pin['repository']], target)
    if run(['git', 'status', '--porcelain'], target, capture=True):
        raise RuntimeError(f'Dependency checkout has changes: {target}')
    if run(['git', 'remote', 'get-url', 'origin'], target, capture=True) != pin['repository']:
        raise RuntimeError(f'Unexpected dependency remote: {target}')
    current = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=target,
                             env=ENV, capture_output=True, text=True)
    if current.returncode or current.stdout.strip() != pin['revision']:
        run(['git', 'fetch', '--depth', '1', 'origin', pin['revision']], target)
        run(['git', 'checkout', '--detach', pin['revision']], target)
    assert run(['git', 'rev-parse', 'HEAD'], target, capture=True) == pin['revision']
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=int, default=min(8, os.cpu_count() or 1))
    p.add_argument('--web', action='store_true', help='also build Tide WASI for cross-platform validation')
    p.add_argument('--fetch-only', action='store_true')
    args = p.parse_args()
    if args.jobs < 1:
        p.error('--jobs must be positive')
    pins = json.loads((ROOT / 'dependencies.json').read_text())
    deps = {name: fetch(name, pins[name]) for name in ('tide', 'flecs', 'entt')}
    if args.fetch_only:
        return
    clang = compiler('clang')
    companion = Path(clang).parent / ('clang++.exe' if os.name == 'nt' else 'clang++')
    if not companion.is_file():
        raise RuntimeError(f'clang++ must be installed alongside clang: {companion}')
    clangpp = str(companion)
    ENV['PATH'] = str(Path(clang).parent) + os.pathsep + ENV['PATH']
    ENV['LLVM_ROOT'] = str(Path(clang).parent.parent)
    if os.environ.get('CFLAGS') or os.environ.get('CXXFLAGS') or os.environ.get('LDFLAGS'):
        raise RuntimeError('Unset CFLAGS/CXXFLAGS/LDFLAGS to keep recorded compiler flags reproducible')
    cargo_overrides = [key for key, value in os.environ.items() if value and (
        key in ('CARGO_ENCODED_RUSTFLAGS', 'RUSTC', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'CARGO_INCREMENTAL')
        or key.startswith(('CARGO_PROFILE_RELEASE_', 'CARGO_BUILD_RUSTC')))]
    if cargo_overrides:
        raise RuntimeError('Unset compiler/profile overrides for a reproducible build: ' + ', '.join(sorted(cargo_overrides)))
    (ROOT / 'build').mkdir(exist_ok=True)
    tide = deps['tide']
    native = tide / 'build/release'
    targets = ['versus_particles', 'versus_wide_lasting', 'versus_churn']
    run(['cmake', '--preset', 'release', '-DTIDE_EXTERNAL_DIRS=', '-DTIDE_DOC_EXAMPLES=OFF'], tide)
    run(['cmake', '--build', '--preset', 'release', '--parallel', args.jobs, '--target', *targets], tide)
    run(['cmake', '-S', ROOT, '-B', ROOT / 'build/cpp', '-G', 'Ninja',
         '-DCMAKE_BUILD_TYPE=Release', f'-DCMAKE_C_COMPILER={clang}', f'-DCMAKE_CXX_COMPILER={clangpp}'])
    run(['cmake', '--build', ROOT / 'build/cpp', '--parallel', args.jobs])
    rust = pins['bevy']['rust']
    rust_version = run(['rustc', '+' + rust, '-vV'], capture=True)
    ENV['RUSTFLAGS'] = '-C target-cpu=x86-64 -C target-feature=-fma' if platform.machine().lower() in ('amd64', 'x86_64') else '-C target-cpu=generic'
    ENV['TIDE_BENCH_RUSTC_VERSION'] = rust_version.splitlines()[0]
    run(['cargo', '+' + rust, 'build', '--locked', '--release', '--manifest-path', ROOT / 'bevy/Cargo.toml',
         '--target-dir', ROOT / 'build/bevy'])
    ext = '.exe' if os.name == 'nt' else ''
    engines = {'Tide': {n: str((native / f'bin/versus_{"wide_lasting" if n == "wide" else n}{ext}').relative_to(ROOT)) for n in ('particles', 'wide', 'churn')},
               'Bevy': {'executable': f'build/bevy/release/tide-bevy-bench{ext}'},
               'Flecs': {'executable': f'build/cpp/bin/flecs-bench{ext}'},
               'EnTT': {'executable': f'build/cpp/bin/entt-bench{ext}'}}
    web = None
    if args.web:
        node = shutil.which('node')
        if not node:
            raise RuntimeError('Node 24.22.1 or newer 24.x is required for WASI validation')
        version = run([node, '--version'], capture=True).lstrip('v').split('.')
        if int(version[0]) != 24 or tuple(map(int, version[1:])) < (22, 1):
            raise RuntimeError('Use Node 24.22.1 or newer 24.x for WASI validation')
        run(['cmake', '--preset', 'web-release', '-DTIDE_EXTERNAL_DIRS=', '-DTIDE_DOC_EXAMPLES=OFF'], tide)
        run(['cmake', '--build', '--preset', 'web-release', '--parallel', args.jobs, '--target', *targets], tide)
        web = {'node': node, 'runner': str((tide / 'cmake/run_wasi.mjs').relative_to(ROOT)),
               **{n: str((tide / f'build/web-release/bin/versus_{"wide_lasting" if n == "wide" else n}.wasm').relative_to(ROOT)) for n in ('particles', 'wide', 'churn')}}
    files = set()
    # Pin relevant sources in addition to immutable dependency commits and binaries.
    # Historical benchmark logs and game assets are not inputs to these targets.
    for dep_name, dep in deps.items():
        for name in run(['git', 'ls-files'], dep, capture=True).splitlines():
            path = dep / name
            relevant = path.suffix in ('.c', '.h', '.cpp', '.hpp', '.inc', '.tide', '.cmake') or path.name in ('CMakeLists.txt', 'CMakePresets.json', 'VERSION')
            if dep_name == 'tide':
                relevant = relevant and not name.startswith(('bench/results/', 'compiler/tests/', 'tests/', 'examples/', 'docs/', 'packages/'))
            elif dep_name == 'flecs':
                relevant = relevant and name.startswith(('src/', 'include/', 'distr/'))
            elif dep_name == 'entt':
                relevant = relevant and name.startswith(('src/', 'single_include/'))
            if relevant and path.is_file():
                files.add(path)
    for folder in ('cpp', 'bevy', 'scripts'):
        files.update(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.update(ROOT / f for f in ('CMakeLists.txt', 'dependencies.json'))
    for entry in engines.values():
        files.update(ROOT / value for value in entry.values())
    for path in (native, ROOT / 'build/cpp'):
        files.update(path / name for name in ('CMakeCache.txt', 'compile_commands.json', 'build.ninja') if (path / name).exists())
    for name in targets:
        files.update(p for p in (native / f'bench/versus/tide/{name}').rglob('*') if p.is_file())
    if web:
        files.update(ROOT / web[n] for n in ('runner', 'particles', 'wide', 'churn'))
    cpu = platform.processor()
    if os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            cpu = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    manifest = {'schema': 1, 'engines': engines, 'files': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in sorted(files)},
                'metadata': {'dependencies': pins, 'tide_revision': pins['tide']['revision'],
                             'benchmark_revision': run(['git', 'rev-parse', 'HEAD'], capture=True),
                             'benchmark_tracked_changes': run(['git', 'status', '--porcelain', '--untracked-files=no'], capture=True),
                             'cpu': cpu, 'os': platform.platform(),
                             'clang': run([clang, '--version'], capture=True), 'rustc': rust_version,
                             'rustflags': ENV['RUSTFLAGS'], 'node': run(['node', '--version'], capture=True) if web else None,
                             'scope': 'ECS update and deferred structural work; excludes hashing/snapshots/network/render; fixed frozen membership'}}
    if web:
        manifest['web'] = web
    (ROOT / 'build/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Built pinned dependencies and wrote build/manifest.json')


if __name__ == '__main__':
    main()
