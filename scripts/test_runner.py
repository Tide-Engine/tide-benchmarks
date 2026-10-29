#!/usr/bin/env python3
"""Negative evidence tests; never launches a performance workload."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
from analyze import check_result, load, validate_attempt, validate_suite
from run import ROOT, arguments, busy, rotation, save, sha


ENGINES = ["Tide", "Bevy", "Flecs", "EnTT"]
CASE = {"id": "particles-1m", "workload": "particles", "count": 1000000, "rate": 0, "tagged": 0, "frozen": 0, "threads": 1}
SETTINGS = {"rounds": 4, "warmup": 200, "ticks": 2, "quiet_seconds": 15, "quiet_timeout": 600, "process_timeout": 300}


def make_fixture(directory):
    directory.mkdir(parents=True)
    engines, binaries, files = {}, {}, {"cpp/common.hpp": "a" * 64}
    for i, engine in enumerate(ENGINES):
        slots = ("particles", "wide", "churn") if engine == "Tide" else ("executable",)
        engines[engine], binaries[engine] = {}, {}
        for slot in slots:
            path = str(directory / "fake-build" / f"{engine}-{slot}")
            digest = hashlib.sha256(path.encode()).hexdigest()
            engines[engine][slot] = path
            binaries[engine][slot] = {"path": path, "sha256": digest}
            files[path] = digest
    manifest = {"schema": 1, "engines": engines, "files": copy.deepcopy(files), "metadata": {"test_only": True}}
    save(directory / "manifest.json", manifest)
    manifest_hash = sha(directory / "manifest.json")
    suite = {"schema": 1, "complete": True, "engines": ENGINES, "cases": [CASE], "settings": SETTINGS,
             "manifest_sha256": manifest_hash, "accepted": ["particles-1m/attempt-1"], "rejected": [],
             "started": "2026-10-29T00:00:00+00:00", "finished": "2026-10-29T00:10:00+00:00"}
    save(directory / "suite.json", suite)
    attempt = directory / "particles-1m/attempt-1"
    (attempt / "raw").mkdir(parents=True)
    meta = {"schema": 1, "complete": True, "case": CASE, "engines": ENGINES, "settings": SETTINGS,
            "manifest_sha256": manifest_hash, "input_hashes": files, "input_hashes_end": copy.deepcopy(files),
            "executables": binaries, "poll_ms": 250, "started": "2026-10-29T00:00:00+00:00",
            "finished": "2026-10-29T00:10:00+00:00"}
    save(attempt / "metadata.json", meta)
    rows = []
    for i in range(16):
        round_number, order = i // 4 + 1, i % 4
        shift = round_number - 1
        engine = (ENGINES[shift:] + ENGINES[:shift])[order]
        if engine == "Tide":
            result = {"benchmark": "versus_particles", "digest": "0x1234567890abcdef", "ok": True, "optimized": True,
                      "options": {"count": 1000000, "warmup": 200, "ticks": 2, "kept": 0, "split": False},
                      "runs": [{"threads": 1, "ways": {"Tide": {"median_ms": 2.0, "mean_ms": 2.0},
                                                       "C": {"median_ms": 1.5, "mean_ms": 1.5}}}]}
        else:
            result = {"benchmark": "versus_particles", "workload": "particles", "count": 1000000, "threads": 1,
                      "warmup": 200, "ticks": 2, "digest": "0x1234567890abcdef", "median_ms": 2.0, "mean_ms": 2.0,
                      "samples_ms": [1.0, 3.0], "entity_count": 1000000, "moving_count": 1000000, "frozen_count": 0,
                      "pool_workers": 0}
        stdout = f"raw/r{round_number}-{engine}.stdout"
        stderr = f"raw/r{round_number}-{engine}.stderr"
        (attempt / stdout).write_text(json.dumps(result) + "\n", encoding="utf-8")
        (attempt / stderr).write_bytes(b"")
        binary = binaries[engine]["particles" if engine == "Tide" else "executable"]
        command = [binary["path"], "--threads", "1", "--warmup", "200", "--ticks", "2", "--count", "1000000"]
        command += ["--json"] if engine == "Tide" else ["--workload", "particles"]
        rows.append({"case": CASE["id"], "engine": engine, "round": round_number, "order": order,
                     "command": command, "executable_sha256": binary["sha256"],
                     "started": f"2026-10-29T00:00:{i*2:02}+00:00", "finished": f"2026-10-29T00:00:{i*2+1:02}+00:00",
                     "elapsed_seconds": 1.0, "stdout": stdout, "stdout_sha256": sha(attempt / stdout),
                     "stderr": stderr, "stderr_sha256": sha(attempt / stderr), "exit_code": 0, "timed_out": False,
                     "parse_error": None, "result": result, "contended": False, "contention": []})
    write_rows(attempt, rows)
    return attempt, rows


def write_rows(attempt, rows):
    (attempt / "records.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.test_root = (ROOT / "build/runner-tests").resolve()
        self.test_root.mkdir(parents=True, exist_ok=True)
        self.base = Path(tempfile.mkdtemp(dir=self.test_root)).resolve()
        self.directory = self.base / "results"
        self.attempt, self.rows = make_fixture(self.directory)

    def tearDown(self):
        self.assertTrue(self.base.is_relative_to(self.test_root))
        shutil.rmtree(self.base)

    def reject(self):
        with self.assertRaises((ValueError, KeyError, OSError, TypeError)):
            validate_suite(self.directory)

    def rewrite_result(self, index):
        row = self.rows[index]
        (self.attempt / row["stdout"]).write_text(json.dumps(row["result"]) + "\n", encoding="utf-8")
        row["stdout_sha256"] = sha(self.attempt / row["stdout"])
        write_rows(self.attempt, self.rows)

    def test_valid_complete_balanced_case(self):
        summary = validate_suite(self.directory)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["processes"], 16)
        self.assertEqual(summary["cases"][0]["engines"]["Bevy"]["median_ms"], 2)

    def test_missing_process(self):
        write_rows(self.attempt, self.rows[:-1])
        self.reject()

    def test_extra_process(self):
        write_rows(self.attempt, self.rows + [self.rows[0]])
        self.reject()

    def test_contended_process(self):
        self.rows[3]["contended"] = True
        self.rows[3]["contention"] = [{"processes": ["clang:123"]}]
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_incomplete_suite(self):
        suite = load(self.directory / "suite.json")
        suite["complete"] = False
        save(self.directory / "suite.json", suite)
        self.reject()

    def test_incomplete_attempt(self):
        meta = load(self.attempt / "metadata.json")
        meta["complete"] = False
        save(self.attempt / "metadata.json", meta)
        self.reject()

    def test_raw_output_tamper(self):
        path = self.attempt / self.rows[0]["stdout"]
        path.write_text(path.read_text() + "changed\n")
        self.reject()

    def test_result_tamper_without_raw_change(self):
        self.rows[1]["result"]["median_ms"] = 99
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_false_sample_statistics(self):
        self.rows[1]["result"]["median_ms"] = 99
        self.rewrite_result(1)
        self.reject()

    def test_wrong_digest(self):
        self.rows[1]["result"]["digest"] = "0x1111111111111111"
        self.rewrite_result(1)
        self.reject()

    def test_changed_command(self):
        self.rows[0]["command"][-2] = "17"
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_different_options_in_output(self):
        self.rows[1]["result"]["count"] = 17
        self.rewrite_result(1)
        self.reject()

    def test_wrong_binary_hash(self):
        self.rows[0]["executable_sha256"] = "f" * 64
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_input_changed(self):
        meta = load(self.attempt / "metadata.json")
        meta["input_hashes_end"]["cpp/common.hpp"] = "b" * 64
        save(self.attempt / "metadata.json", meta)
        self.reject()

    def test_unbalanced_launch_order(self):
        self.rows[0], self.rows[1] = self.rows[1], self.rows[0]
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_overlapping_processes(self):
        self.rows[1]["started"] = self.rows[0]["started"]
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_raw_path_escape(self):
        self.rows[0]["stdout"] = "../../outside.stdout"
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_nonempty_stderr(self):
        path = self.attempt / self.rows[0]["stderr"]
        path.write_text("unexpected diagnostic\n")
        self.rows[0]["stderr_sha256"] = sha(path)
        write_rows(self.attempt, self.rows)
        self.reject()

    def test_nan_sample(self):
        self.rows[1]["result"]["samples_ms"][0] = float("nan")
        self.rewrite_result(1)
        self.reject()

    def test_wrong_population(self):
        self.rows[1]["result"]["entity_count"] = 999999
        self.rewrite_result(1)
        self.reject()

    def test_wrong_bevy_workers(self):
        self.rows[1]["result"]["pool_workers"] = 4
        self.rewrite_result(1)
        self.reject()

    def test_failed_tide_reference(self):
        self.rows[0]["result"]["ok"] = False
        self.rewrite_result(0)
        self.reject()

    def test_manifest_tamper(self):
        (self.directory / "manifest.json").write_text("{}\n")
        self.reject()

    def test_omitted_attempt_evidence(self):
        extra = self.directory / "particles-1m/attempt-2"
        extra.mkdir()
        save(extra / "metadata.json", {"complete": False})
        self.reject()

    def test_retry_without_preceding_rejection(self):
        replacement = self.directory / "particles-1m/attempt-2"
        self.attempt.rename(replacement)
        suite = load(self.directory / "suite.json")
        suite["accepted"] = ["particles-1m/attempt-2"]
        save(self.directory / "suite.json", suite)
        self.reject()

    def test_rotation_balances_all_launch_positions(self):
        for engine in ENGINES:
            self.assertEqual(sorted(rotation(r).index(engine) for r in range(1, 5)), [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main()
