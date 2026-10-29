#!/usr/bin/env python3
"""Validate stored evidence before computing any ECS performance comparisons."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
from run import CASES, ENGINES, arguments, executable, rotation, save, sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, positive=True):
    require(type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0), f"{name}: invalid timing")
    return value


def hash_string(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_child(directory, relative):
    require(isinstance(relative, str) and relative, "Missing evidence path")
    path = (directory / relative).resolve()
    require(path.is_relative_to(directory.resolve()), f"Evidence path escapes directory: {relative}")
    return path


def date(text):
    parsed = dt.datetime.fromisoformat(text)
    require(parsed.tzinfo is not None, "Timestamps must include UTC offsets")
    return parsed


def check_result(result, engine, case, warmup, ticks, measured=True):
    name = f"{case['id']}/{engine}"
    require(isinstance(result, dict), f"{name}: missing JSON result")
    require(re.fullmatch(r"0x[0-9a-f]{16}", str(result.get("digest"))) is not None, f"{name}: invalid digest")
    require(result.get("benchmark") == "versus_" + case["workload"], f"{name}: wrong benchmark")
    options = result.get("options", {}) if engine == "Tide" else result
    expected = {"warmup": warmup, "ticks": ticks}
    if case["workload"] == "churn":
        expected["rate"] = case["rate"]
    else:
        expected["count"] = case["count"]
    if case["workload"] == "wide":
        expected.update(tagged=case["tagged"], frozen=case["frozen"])
    require(all(type(options.get(k)) is int and options[k] == v for k, v in expected.items()), f"{name}: workload options differ")
    if engine == "Tide":
        require(result.get("ok") is True and result.get("optimized") is True, f"{name}: Tide/C validation or optimized build failed")
        require(options.get("kept") == 0 and options.get("split") is False, f"{name}: unexpected snapshots or forced splitting")
        runs = result.get("runs")
        require(isinstance(runs, list) and len(runs) == 1 and runs[0].get("threads") == case["threads"], f"{name}: wrong execution budget")
        ways = runs[0].get("ways", {})
        require(set(ways) == {"Tide", "C"}, f"{name}: unexpected implementation set")
        for way, timing in ways.items():
            for key in ("median_ms", "mean_ms"):
                number(timing[key], f"{name}/{way}/{key}", positive=measured)
        return ways["Tide"]["median_ms"]
    require(result.get("workload") == case["workload"] and result.get("threads") == case["threads"], f"{name}: wrong workload or execution budget")
    if "engine" in result:
        require(str(result["engine"]).casefold() == engine.casefold(), f"{name}: wrong engine")
    for key in ("median_ms", "mean_ms"):
        number(result.get(key), f"{name}/{key}", positive=measured)
    samples = result.get("samples_ms")
    require(isinstance(samples, list) and len(samples) == ticks, f"{name}: wrong sample count")
    for sample in samples:
        number(sample, f"{name}/sample", positive=False)
    for key, statistic in (("median_ms", statistics.median), ("mean_ms", statistics.mean)):
        require(math.isclose(result[key], statistic(samples), rel_tol=1e-8, abs_tol=1.1e-9), f"{name}: {key} disagrees with samples")
    for key in ("entity_count", "frozen_count", "moving_count"):
        require(type(result.get(key)) is int and result[key] >= 0, f"{name}: invalid {key}")
    require(result["entity_count"] == result["frozen_count"] + result["moving_count"], f"{name}: entity count partition differs")
    if case["workload"] != "churn":
        require(result["entity_count"] == case["count"], f"{name}: entity count differs")
    if case["workload"] != "wide" or not case["tagged"]:
        require(result["frozen_count"] == 0, f"{name}: unexpected frozen entities")
    if engine == "Bevy":
        require(result.get("pool_workers") == case["threads"] - 1, f"{name}: wrong Bevy worker budget")
    return result["median_ms"]


def check_raw(directory, row):
    stdout = safe_child(directory, row["stdout"])
    stderr = safe_child(directory, row["stderr"])
    require(hash_string(row.get("stdout_sha256")) and sha(stdout) == row["stdout_sha256"], "Raw stdout SHA-256 differs")
    require(hash_string(row.get("stderr_sha256")) and sha(stderr) == row["stderr_sha256"], "Raw stderr SHA-256 differs")
    require(stderr.stat().st_size == 0, "Successful measured process wrote to stderr")
    candidates = [line for line in stdout.read_text(encoding="utf-8-sig").splitlines() if line.startswith("{")]
    require(len(candidates) == 1 and json.loads(candidates[0]) == row["result"], "Raw output and saved result differ")


def validate_attempt(directory):
    directory = Path(directory)
    meta = load(directory / "metadata.json")
    require(meta.get("schema") == 1 and meta.get("complete") is True and "error" not in meta, "Attempt is incomplete or failed")
    require(meta.get("engines") == ENGINES, "Wrong engine list or order")
    settings = meta["settings"]
    rounds, warmup, ticks = (settings[k] for k in ("rounds", "warmup", "ticks"))
    require(all(type(x) is int and x > 0 for x in (rounds, warmup, ticks)) and rounds % 4 == 0, "Invalid counts or unbalanced rounds")
    require(meta.get("poll_ms") == 250, "Unexpected contention sampling interval")
    for key in ("quiet_seconds", "quiet_timeout", "process_timeout"):
        number(settings[key], key)
    case = meta["case"]
    require(case in CASES, "Unknown or modified measured workload")
    require(hash_string(meta.get("manifest_sha256")), "Missing manifest identity")
    files = meta.get("input_hashes")
    require(isinstance(files, dict) and files and all(hash_string(v) for v in files.values()), "Invalid input identities")
    require(meta.get("input_hashes_end") == files, "Measured inputs changed or end identities are absent")
    binaries = meta["executables"]
    require(set(binaries) == set(ENGINES), "Missing engine identities")
    for engine in ENGINES:
        expected_slots = {"particles", "wide", "churn"} if engine == "Tide" else {"executable"}
        require(set(binaries[engine]) == expected_slots, f"{engine}: wrong binary slots")
        for binary in binaries[engine].values():
            require(isinstance(binary.get("path"), str) and hash_string(binary.get("sha256")), "Invalid executable identity")
            require(files.get(binary["path"]) == binary["sha256"], "Executable absent from input pins")
    rows = [json.loads(line) for line in (directory / "records.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    require(len(rows) == rounds * len(ENGINES), "Incomplete or extra process records")
    require(date(meta["started"]) <= date(meta["finished"]), "Attempt timestamps reversed")
    by_round = {}
    previous_end = date(meta["started"])
    for i, row in enumerate(rows):
        round_number, order = divmod(i, len(ENGINES))
        round_number += 1
        engine = rotation(round_number)[order]
        require(row.get("case") == case["id"] and row.get("engine") == engine and row.get("round") == round_number and row.get("order") == order,
                "Process records do not follow the declared balanced order")
        require(row.get("exit_code") == 0 and row.get("timed_out") is False and row.get("parse_error") is None, "Failed or timed-out process")
        require(row.get("contended") is False and row.get("contention") == [], "Contended or unmarked process")
        binary = executable(binaries, engine, case)
        require(row.get("executable_sha256") == binary["sha256"], "Executable hash differs")
        require(row.get("command") == [binary["path"], *arguments(engine, case, warmup, ticks)], "Command or workload flags differ")
        begin, end = date(row["started"]), date(row["finished"])
        require(previous_end <= begin <= end <= date(meta["finished"]), "Process timestamps overlap or escape attempt")
        previous_end = end
        number(row["elapsed_seconds"], "Process elapsed time")
        check_raw(directory, row)
        check_result(row["result"], engine, case, warmup, ticks)
        by_round.setdefault(round_number, {})[engine] = row["result"]
    digests = {row["result"]["digest"] for row in rows}
    require(len(digests) == 1, "Logical digest mismatch across engines or rounds")
    counts = {(r["entity_count"], r["frozen_count"], r["moving_count"])
              for group in by_round.values() for engine, r in group.items() if engine != "Tide"}
    require(len(counts) == 1, "Entity/frozen counts differ across engines or rounds")
    values = {engine: [] for engine in ENGINES}
    c_values = []
    for group in by_round.values():
        values["Tide"].append(group["Tide"]["runs"][0]["ways"]["Tide"]["median_ms"])
        c_values.append(group["Tide"]["runs"][0]["ways"]["C"]["median_ms"])
        for engine in ENGINES[1:]:
            values[engine].append(group[engine]["median_ms"])
    stats = {}
    for engine, measurements in values.items():
        stats[engine] = {"median_ms": statistics.median(measurements), "range_ms": [min(measurements), max(measurements)],
                         "process_medians_ms": measurements}
        if engine != "Tide":
            ratios = [x / y for x, y in zip(measurements, values["Tide"])]
            stats[engine]["paired_ratio_over_tide"] = statistics.median(ratios)
            stats[engine]["paired_ratios_over_tide"] = ratios
    return {"valid": True, **case, "rounds": rounds, "warmup": warmup, "ticks": ticks,
            "processes": len(rows), "digest": digests.pop(), "entity_count": next(iter(counts))[0],
            "frozen_count": next(iter(counts))[1], "engines": stats,
            "c_reference": {"median_ms": statistics.median(c_values), "range_ms": [min(c_values), max(c_values)],
                            "process_medians_ms": c_values, "scope": "Timed after Tide in the same process; contextual reference, not independently rotated"}}


def validate_suite(directory):
    directory = Path(directory)
    suite = load(directory / "suite.json")
    require(suite.get("schema") == 1 and suite.get("complete") is True and "error" not in suite, "Suite is incomplete or failed")
    require(suite.get("engines") == ENGINES, "Wrong suite engines")
    require(sha(directory / "manifest.json") == suite.get("manifest_sha256"), "Saved build manifest hash differs")
    manifest = load(directory / "manifest.json")
    require(manifest.get("schema") == 1 and set(manifest.get("engines", {})) == set(ENGINES), "Invalid saved build manifest")
    cases, accepted, rejected = suite["cases"], suite["accepted"], suite["rejected"]
    require(cases and all(c in CASES for c in cases) and len({c["id"] for c in cases}) == len(cases), "Invalid suite cases")
    require(cases == [c for c in CASES if c["id"] in {v["id"] for v in cases}], "Suite case order differs from the predeclared order")
    require(isinstance(accepted, list) and len(accepted) == len(cases) and len(set(accepted)) == len(accepted), "Missing or duplicate accepted batches")
    require(isinstance(rejected, list) and len(set(rejected)) == len(rejected) and not set(accepted) & set(rejected), "Invalid rejected batch list")
    listed = set(accepted) | set(rejected)
    actual = {str(p.parent.relative_to(directory)).replace("\\", "/") for p in directory.glob("*/attempt-*/metadata.json")}
    require(listed == actual, "Attempt evidence is omitted from or added to the suite ledger")
    for case, relative in zip(cases, accepted):
        require(re.fullmatch(re.escape(case["id"]) + r"/attempt-[1-3]", relative) is not None, "Accepted batch has unexpected case/path")
        accepted_number = int(relative.rsplit("-", 1)[1])
        expected_rejected = {f"{case['id']}/attempt-{i}" for i in range(1, accepted_number)}
        actual_rejected = {p for p in rejected if p.startswith(case["id"] + "/")}
        require(actual_rejected == expected_rejected, "Retry history is missing, reordered or extends past acceptance")
    summaries = []
    identity = None
    for case, relative in zip(cases, accepted):
        attempt = safe_child(directory, relative)
        require(re.fullmatch(re.escape(case["id"]) + r"/attempt-[1-3]", relative) is not None, "Accepted batch has unexpected case/path")
        meta = load(attempt / "metadata.json")
        require(meta["manifest_sha256"] == suite["manifest_sha256"] and meta["settings"] == suite["settings"] and meta["case"] == case,
                "Accepted batch metadata differs from suite")
        current = (meta["input_hashes"], meta["executables"])
        require(identity is None or current == identity, "Measured sources or binaries differ between accepted cases")
        identity = current
        for name, digest in manifest["files"].items():
            require(meta["input_hashes"].get(name) == digest, "Manifest input pin is absent or changed")
        summary = validate_attempt(attempt)
        summary["evidence"] = relative
        summaries.append(summary)
    for relative in rejected:
        attempt = safe_child(directory, relative)
        meta = load(attempt / "metadata.json")
        require(meta.get("complete") is False and str(meta.get("error", "")).startswith("ContentionError:"), "Rejected batch was not an explicit contention failure")
        rows = [json.loads(s) for s in (attempt / "records.jsonl").read_text(encoding="utf-8-sig").splitlines() if s.strip()]
        require(any(row.get("contended") is True and row.get("contention") for row in rows), "Rejected batch lacks contention evidence")
    return {"schema": 1, "valid": True, "processes": sum(c["processes"] for c in summaries),
            "rounds": suite["settings"]["rounds"], "warmup": suite["settings"]["warmup"], "ticks": suite["settings"]["ticks"],
            "engines": ENGINES, "manifest_sha256": suite["manifest_sha256"], "metadata": manifest.get("metadata", {}),
            "scope": "Single-thread ECS ticks, including deferred churn changes; fixed frozen membership. Setup, digest, hashing, snapshots, rollback, networking and rendering excluded.",
            "estimator": "Median of process medians; range is process-median min/max. Each implementation occupies every launch position once per four rounds.",
            "cases": summaries, "excluded_attempts": rejected}


def markdown(summary):
    lines = ["# ECS CPU comparison", "", summary["scope"], "", summary["estimator"], "",
             f"{summary['processes']} accepted processes; {summary['rounds']} rounds; {summary['warmup']} warmup and {summary['ticks']} measured ticks per process.", "",
             "Milliseconds per tick; lower is faster. Parentheses show process-median ranges.", "",
             "| Workload | Tide | Bevy | Flecs | EnTT |", "| --- | ---: | ---: | ---: | ---: |"]
    for case in summary["cases"]:
        cells = []
        for engine in ENGINES:
            s = case["engines"][engine]
            cells.append(f"{s['median_ms']:.6f} ({s['range_ms'][0]:.6f}–{s['range_ms'][1]:.6f})")
        lines.append("| " + case["id"] + " | " + " | ".join(cells) + " |")
    lines += ["", "All accepted logical digests agree across implementations and rounds. These digests do not establish equal entity IDs, row order, serialization, or cross-platform determinism for the other libraries.", "",
              "Tide and Bevy use their scheduled tick. Flecs uses its systems/pipeline; EnTT uses explicit tick dispatch and owning groups. See the source and methodology for these differences. No aggregate engine ranking is computed.", "",
              f"Excluded contended attempts: {len(summary['excluded_attempts'])}. Raw output and launch metadata remain in each case directory."]
    return "\n".join(lines) + "\n"


def write_summary(directory):
    directory = Path(directory)
    summary = validate_suite(directory)
    save(directory / "summary.json", summary)
    (directory / "summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    args = parser.parse_args()
    try:
        summary = write_summary(args.directory)
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        print(f"Invalid comparison: {error}", file=sys.stderr)
        directory = Path(args.directory)
        if directory.is_dir():
            save(directory / "summary.json", {"valid": False, "error": str(error)})
            (directory / "summary.md").write_text(f"Invalid comparison: {error}\n", encoding="utf-8")
        return 1
    print(markdown(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
