#!/usr/bin/env python3
"""Run fixed ECS workloads in balanced, independently validated case batches."""
import argparse
import contextlib
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
ENGINES = ["Tide", "Bevy", "Flecs", "EnTT"]
CASES = [
    {"id": "particles-1m", "workload": "particles", "count": 1000000, "rate": 0, "tagged": 0, "frozen": 0, "threads": 1},
    {"id": "wide-1m", "workload": "wide", "count": 1000000, "rate": 0, "tagged": 0, "frozen": 0, "threads": 1},
    *[{"id": f"filtered{f}-1m", "workload": "wide", "count": 1000000, "rate": 0, "tagged": 1, "frozen": f, "threads": 1} for f in (50, 95, 99)],
    {"id": "churn-2k", "workload": "churn", "count": 0, "rate": 2000, "tagged": 0, "frozen": 0, "threads": 1},
]
BUSY_NAMES = {"ninja", "clang", "clang++", "clang-cl", "lld-link", "link", "cmake", "ctest", "cargo", "rustc", "tide_tests", "tidec", "gcc", "g++", "cc1", "cc1plus", "make"}
BUSY_PREFIX = re.compile(r"^(bench_|versus_|tidec_|tide_platform_|tide[-_]bevy[-_]bench|flecs[-_]bench|entt[-_]bench)")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def resolve(path):
    p = Path(path)
    return p.resolve() if p.is_absolute() else (ROOT / p).resolve()


def load_manifest(path):
    path = resolve(path)
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != 1 or set(manifest.get("engines", {})) != set(ENGINES):
        raise ValueError("Manifest must contain schema 1 and exactly Tide, Bevy, Flecs and EnTT")
    if not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise ValueError("Manifest must pin measured files")
    files = dict(manifest["files"])
    files[str(path)] = sha(path)
    for script in ("run.py", "analyze.py", "validate.py"):
        p = ROOT / "scripts" / script
        files[str(p)] = sha(p)
    executables = {}
    for engine in ENGINES:
        entry = manifest["engines"][engine]
        slots = ("particles", "wide", "churn") if engine == "Tide" else ("executable",)
        executables[engine] = {}
        for slot in slots:
            p = resolve(entry[slot])
            digest = sha(p)
            executables[engine][slot] = {"path": str(p), "sha256": digest}
            if str(p) in files and files[str(p)] != digest:
                raise ValueError(f"Manifest binary hash differs: {p}")
            files[str(p)] = digest
    verify_files(files)
    return path, manifest, files, executables


def verify_files(files):
    for name, expected in files.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Invalid SHA-256 for {name}")
        if sha(resolve(name)) != expected:
            raise ValueError(f"Measured input changed: {name}")


def arguments(engine, case, warmup, ticks):
    args = ["--threads", str(case["threads"]), "--warmup", str(warmup), "--ticks", str(ticks)]
    args += ["--rate", str(case["rate"])] if case["workload"] == "churn" else ["--count", str(case["count"])]
    if case["workload"] == "wide":
        args += ["--tagged", str(case["tagged"]), "--frozen", str(case["frozen"])]
    args += ["--json"] if engine == "Tide" else ["--workload", case["workload"]]
    return args


def executable(executables, engine, case):
    return executables[engine][case["workload"] if engine == "Tide" else "executable"]


def parse_result(raw):
    lines = [line for line in raw.decode("utf-8-sig").splitlines() if line.startswith("{")]
    if len(lines) != 1:
        raise ValueError("Expected exactly one JSON output record")
    return json.loads(lines[0])


def rotation(round_number):
    offset = (round_number - 1) % len(ENGINES)
    return ENGINES[offset:] + ENGINES[:offset]


def windows_processes():
    """Native process-name inventory; no injected probes or spawned shell per poll."""
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                    ("heap", ctypes.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
                    ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD),
                    ("exe", w.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32FirstW.restype = w.BOOL
    kernel.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(Entry)
        if not kernel.Process32FirstW(handle, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            yield entry.pid, entry.exe
            if not kernel.Process32NextW(handle, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(ctypes.get_last_error())
                break
    finally:
        kernel.CloseHandle(handle)


def busy(owned=0):
    if os.name == "nt":
        processes = windows_processes()
    else:
        result = subprocess.run(["ps", "-A", "-o", "pid=,comm="], capture_output=True, text=True, check=True)
        processes = [(int(line.split(None, 1)[0]), line.split(None, 1)[1])
                     for line in result.stdout.splitlines() if len(line.split(None, 1)) == 2]
    found = []
    for pid, name in processes:
        name = Path(name).name.lower()
        if name.endswith(".exe"):
            name = name[:-4]
        if pid not in (owned, os.getpid()) and (name in BUSY_NAMES or BUSY_PREFIX.match(name)):
            found.append(f"{name}:{pid}")
    return sorted(found)


@contextlib.contextmanager
def gate(timeout=600):
    if os.name == "nt":
        from ctypes import wintypes as w
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
        kernel.CreateMutexW.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.WaitForSingleObject.restype = w.DWORD
        kernel.ReleaseMutex.argtypes = [w.HANDLE]
        kernel.ReleaseMutex.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        handle = kernel.CreateMutexW(None, False, "Local\\TideClaudeContinuationBenchmark")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        held = False
        try:
            result = kernel.WaitForSingleObject(handle, int(timeout * 1000))
            if result not in (0, 0x80):  # owned, or acquired abandoned mutex
                raise TimeoutError("Benchmark gate was not acquired")
            held = True
            yield
        finally:
            if held:
                kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        import fcntl
        path = Path(tempfile.gettempdir()) / f"tide-benchmarks-{os.getuid()}.lock"
        with path.open("a+b") as lock:
            start = time.monotonic()
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - start >= timeout:
                        raise TimeoutError("Benchmark gate was not acquired")
                    time.sleep(0.25)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def quiet(seconds, timeout, events):
    start = since = time.monotonic()
    while True:
        current = busy()
        now = time.monotonic()
        if current:
            since = now
            events.append({"at": utc(), "processes": current})
        elif now - since >= seconds:
            return
        if now - start >= timeout:
            raise TimeoutError("Quiet-machine guard timed out; no timing result accepted")
        time.sleep(0.25)


class ContentionError(RuntimeError):
    pass


def run_process(directory, engine, case, round_number, order, settings, executables, env):
    binary = executable(executables, engine, case)
    command = [binary["path"], *arguments(engine, case, settings["warmup"], settings["ticks"])]
    stem = f"r{round_number}-{engine}"
    out = directory / "raw" / f"{stem}.stdout"
    err = directory / "raw" / f"{stem}.stderr"
    contention = []
    started, timer = utc(), time.monotonic()
    timed_out = False
    with out.open("wb") as stdout, err.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=CREATE_NO_WINDOW)
        try:
            # Scan immediately and at nominal 250 ms intervals. Very short processes
            # can still evade scans, and other desktop loads are not detected.
            while process.poll() is None:
                found = busy(process.pid)
                if found:
                    contention.append({"at": utc(), "processes": found})
                if time.monotonic() - timer > settings["process_timeout"]:
                    timed_out = True
                    process.kill()
                    break
                try:
                    process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    pass
            process.wait()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    raw = out.read_bytes()
    parse_error = None
    try:
        result = parse_result(raw)
    except (ValueError, UnicodeError) as error:
        result, parse_error = None, str(error)
    record = {"case": case["id"], "engine": engine, "round": round_number, "order": order,
              "command": command, "executable_sha256": sha(binary["path"]),
              "started": started, "finished": utc(), "elapsed_seconds": time.monotonic() - timer,
              "stdout": str(out.relative_to(directory)).replace("\\", "/"), "stdout_sha256": sha(out),
              "stderr": str(err.relative_to(directory)).replace("\\", "/"), "stderr_sha256": sha(err),
              "exit_code": process.returncode, "timed_out": timed_out, "result": result,
              "parse_error": parse_error, "contended": bool(contention), "contention": contention}
    with (directory / "records.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, allow_nan=False) + "\n")
    print(f"{case['id']} round {round_number} {engine}: exit {process.returncode}, contention {bool(contention)}", flush=True)
    if process.returncode or timed_out or parse_error or err.stat().st_size:
        raise RuntimeError(f"Failed process retained: {out} (stderr: {err})")
    if record["executable_sha256"] != binary["sha256"]:
        raise RuntimeError(f"Executable changed during run: {binary['path']}")
    if contention:
        raise ContentionError(f"Contended process retained: {out}")
    return record


def run_attempt(directory, case, settings, manifest_hash, files, executables, env):
    from analyze import check_result, validate_attempt
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "raw").mkdir()
    meta = {"schema": 1, "complete": False, "case": case, "engines": ENGINES,
            "manifest_sha256": manifest_hash, "input_hashes": files, "executables": executables,
            "settings": settings, "started": utc(), "quiet_resets": [],
            "guard": "process-name inventory; arbitrary Node/browser/desktop load is not detected",
            "poll_ms": 250, "order": "cyclic rotation; every engine occupies each position every four rounds"}
    save(directory / "metadata.json", meta)
    try:
        with gate(settings["quiet_timeout"]):
            quiet(settings["quiet_seconds"], settings["quiet_timeout"], meta["quiet_resets"])
            verify_files(files)
            for round_number in range(1, settings["rounds"] + 1):
                records = []
                for order, engine in enumerate(rotation(round_number)):
                    if busy():
                        quiet(settings["quiet_seconds"], settings["quiet_timeout"], meta["quiet_resets"])
                    record = run_process(directory, engine, case, round_number, order, settings, executables, env)
                    check_result(record["result"], engine, case, settings["warmup"], settings["ticks"])
                    records.append(record)
                if len({r["result"]["digest"] for r in records}) != 1:
                    raise RuntimeError(f"Logical digest mismatch: {case['id']}, round {round_number}")
            verify_files(files)
            meta["input_hashes_end"] = dict(files)
            meta["complete"] = True
    except Exception as error:
        meta["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        meta["finished"] = utc()
        save(directory / "metadata.json", meta)
    summary = validate_attempt(directory)
    save(directory / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="build/manifest.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--only", nargs="+", help="Case IDs; defaults to all six cases")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--ticks", type=int, default=400)
    parser.add_argument("--quiet-seconds", type=float, default=15)
    parser.add_argument("--quiet-timeout", type=float, default=600)
    parser.add_argument("--process-timeout", type=float, default=300)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    if args.rounds <= 0 or args.rounds % 4 or min(args.warmup, args.ticks, args.quiet_seconds, args.quiet_timeout, args.process_timeout, args.attempts) <= 0:
        parser.error("rounds must be a positive multiple of four; counts/timeouts must be positive")
    if args.attempts > 3:
        parser.error("at most three contention attempts per case are supported")
    requested = args.only or [c["id"] for c in CASES]
    if len(set(requested)) != len(requested) or set(requested) - {c["id"] for c in CASES}:
        parser.error("duplicate or unknown case ID")
    cases = [c for c in CASES if c["id"] in requested]
    manifest_path, manifest, files, executables = load_manifest(args.manifest)
    output = resolve(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_bytes(manifest_path.read_bytes())
    manifest_hash = sha(output / "manifest.json")
    settings = {k: getattr(args, k) for k in ("rounds", "warmup", "ticks", "quiet_seconds", "quiet_timeout", "process_timeout")}
    suite = {"schema": 1, "complete": False, "cases": cases, "engines": ENGINES, "settings": settings,
             "manifest_sha256": manifest_hash, "started": utc(), "accepted": [], "rejected": [],
             "host": {"os": platform.platform(), "machine": platform.machine(), "processor": platform.processor(), "python": sys.version}}
    save(output / "suite.json", suite)
    env = {**os.environ, "TIDE_HIDDEN": "1", "TIDE_BENCH_REVISION": str(manifest.get("metadata", {}).get("tide_revision", "see-manifest")),
           "TIDE_BENCH_MACHINE": str(manifest.get("metadata", {}).get("cpu", platform.processor()))}
    try:
        for case in cases:
            for attempt in range(1, args.attempts + 1):
                relative = f"{case['id']}/attempt-{attempt}"
                try:
                    run_attempt(output / relative, case, settings, manifest_hash, files, executables, env)
                except ContentionError:
                    suite["rejected"].append(relative)
                    save(output / "suite.json", suite)
                    if attempt == args.attempts:
                        raise
                    continue
                suite["accepted"].append(relative)
                save(output / "suite.json", suite)
                break
        verify_files(files)
        suite["complete"] = True
    except Exception as error:
        suite["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        suite["finished"] = utc()
        save(output / "suite.json", suite)
    from analyze import write_summary
    write_summary(output)
    print(f"Validated suite written to {output}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.SubprocessError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        sys.exit(1)
