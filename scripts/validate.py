#!/usr/bin/env python3
"""Compare logical results on small/edge/steady-state workloads; discard timings."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from analyze import check_result, require
from run import CREATE_NO_WINDOW, ENGINES, ROOT, arguments, executable, load_manifest, parse_result, resolve, save, sha, utc, verify_files


def correctness_cases():
    cases = [{"workload": "particles", "count": n} for n in (1, 17, 10000)]
    cases += [{"workload": "wide", "count": n} for n in (0, 1, 17, 10000)]
    cases += [{"workload": "wide", "count": n, "tagged": 1, "frozen": frozen}
              for n in (0, 17, 10000) for frozen in (0, 50, 95, 99, 100)]
    cases += [{"workload": "churn", "rate": n} for n in (1, 31, 100)]
    for i, case in enumerate(cases):
        yield {"id": f"correctness-{i}", "count": 0, "rate": 0, "tagged": 0, "frozen": 0, "threads": 1, **case}


def call(command):
    result = subprocess.run(command, cwd=ROOT, env={**os.environ, "TIDE_HIDDEN": "1"},
                            capture_output=True, timeout=120, creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f"Correctness process failed ({result.returncode}): {command}\n{result.stdout.decode(errors='replace')}\n{result.stderr.decode(errors='replace')}")
    # Node's experimental WASI warning is permitted only for the optional web
    # invocation, which supplies --no-warnings itself. Other stderr is unexpected.
    if result.stderr:
        raise RuntimeError(f"Unexpected correctness stderr: {command}\n{result.stderr.decode(errors='replace')}")
    parsed = parse_result(result.stdout)
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="build/manifest.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--web", action="store_true", help="Also compare the manifest's native-built Tide WASI targets")
    args = parser.parse_args()
    manifest_path, manifest, files, binaries = load_manifest(args.manifest)
    output = resolve(args.output)
    if output.exists():
        parser.error("Refusing to overwrite correctness evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    web = manifest.get("web")
    if args.web and not web:
        parser.error("--web requires web:{node,runner,particles,wide,churn} in the build manifest")
    if args.web:
        for key in ("node", "runner", "particles", "wide", "churn"):
            path = resolve(web[key])
            files[str(path)] = sha(path)
    report = {"schema": 1, "ok": False, "started": utc(), "manifest_sha256": sha(manifest_path),
              "scope": "Logical result checks only; all collected timings discarded", "web": args.web,
              "engines": ENGINES, "input_hashes": files, "checks": 0, "records": []}
    save(output, report)
    try:
        verify_files(files)
        for case in correctness_cases():
            for warmup, ticks in ((1, 1), (2, 20), (200, 40)):
                results, commands = {}, {}
                for engine in ENGINES:
                    command = [executable(binaries, engine, case)["path"], *arguments(engine, case, warmup, ticks)]
                    result = call(command)
                    check_result(result, engine, case, warmup, ticks, measured=False)
                    results[engine] = result
                    commands[engine] = command
                digests = {r["digest"] for r in results.values()}
                require(len(digests) == 1, f"{case}, warmup {warmup}, ticks {ticks}: digest mismatch {dict((e,r['digest']) for e,r in results.items())}")
                counts = {(r["entity_count"], r["frozen_count"], r["moving_count"]) for e, r in results.items() if e != "Tide"}
                require(len(counts) == 1, f"{case}: entity/frozen counts mismatch")
                if args.web:
                    command = [str(resolve(web["node"])), "--no-warnings", str(resolve(web["runner"])),
                               str(resolve(web[case["workload"]])), *arguments("Tide", case, warmup, ticks)]
                    result = call(command)
                    check_result(result, "Tide", case, warmup, ticks, measured=False)
                    require(result["digest"] in digests, f"{case}: native/WASI digest mismatch")
                    commands["Tide WASI"] = command
                entity_count, frozen_count, moving_count = counts.pop()
                report["records"].append({"case": case, "warmup": warmup, "ticks": ticks, "digest": digests.pop(),
                                          "entity_count": entity_count, "frozen_count": frozen_count, "moving_count": moving_count,
                                          "commands": commands})
                report["checks"] += 1
        verify_files(files)
        report["input_hashes_end"] = dict(files)
        report["ok"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["finished"] = utc()
        save(output, report)
    print(f"Passed {report['checks']} workload/phase cases across four native implementations and Tide/C" + (" plus Tide WASI" if args.web else "") + "; timings discarded.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"Correctness validation failed: {error}", file=sys.stderr)
        sys.exit(1)
