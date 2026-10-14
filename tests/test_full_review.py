"""Failures reproduced during the full implementation review, including provenance."""

from contextlib import redirect_stdout, redirect_stderr
import copy
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import zipfile

from freight_watch.__main__ import main
from freight_watch.bundle import read_bundle, source_files
from freight_watch.engine import analyze, percent, weekly_metrics
from freight_watch.evaluation import evaluate
from freight_watch.evidence import EvidenceMatcher
from freight_watch.io import DATA_DIR, ROOT, decode_json, load_shipments, note_hash, read_csv, write_json
from freight_watch.llm import QuoteWriter, complete_extract
from freight_watch.models import Note, Thresholds
from freight_watch.questions import answer_question
from freight_watch.retrieval import NoteIndex
from scripts.package_submission import build_package, FILES, INPUT_DIR, INPUTS
from scripts.verify_numbers import check_numbers
from tests.test_engine import shipment, temporary_directory


def invoke(*arguments):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return main(list(arguments))


class NumericInputReviewTests(unittest.TestCase):
    def test_underflow_and_overflow_in_transport_work_are_rejected(self):
        for quantity, distance in [(1e-300, 1e-300), (1e300, 1e300)]:
            with self.assertRaisesRegex(ValueError, "tonne-km"):
                weekly_metrics([shipment("1", "A", "B", "2025-01-06", 1000, quantity, distance)])
            with (DATA_DIR / "shipment_records.csv").open(encoding="utf-8-sig", newline="") as stream:
                raw = next(csv.DictReader(stream))
            raw.update(quantity_tonnes=str(quantity), distance_km=str(distance))
            stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(raw))
            writer.writeheader(); writer.writerow(raw)
            with self.assertRaisesRegex(ValueError, "tonne-km"):
                load_shipments("test.csv", stream.getvalue().encode())

    def test_overflowed_totals_and_comparisons_fail_with_validation_errors(self):
        with self.assertRaisesRegex(ValueError, "numeric range"):
            weekly_metrics([shipment(str(i), "A", "B", "2025-01-06", 1e308) for i in range(2)])
        with self.assertRaisesRegex(ValueError, "numeric range"):
            percent(1e308, 1e-308)

    def test_large_representable_average_does_not_overflow(self):
        rows = weekly_metrics([shipment(str(i), str(i), "B", "2025-01-06", 1e308, 1, 1) for i in range(3)])
        self.assertEqual(rows[0]["peer_average"], 1e308)

    def test_extreme_dates_do_not_overflow_calendar_windows(self):
        rows = weekly_metrics([shipment("1", "A", "B", "0001-01-01", 1000),
                               shipment("2", "A", "B", "9999-12-31", 1000)])
        self.assertIsNone(rows[1]["history_average"])
        note = Note("N1", date.max, "A-B", "No freight cost change.")
        rules = {"notes": {"N1": {"supports_cost_increase": False, "exclusion_reason": "No change.", "source_sha256": note_hash(note)}}}
        matcher = EvidenceMatcher([note], None, NoteIndex([note]), rows, config=rules)
        self.assertEqual(matcher.eligibility(note, rows[-1]), (False, "No change."))

    def test_ambiguous_directional_route_labels_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            weekly_metrics([shipment("1", "A-B", "C", "2025-01-06", 1000),
                            shipment("2", "A", "B-C", "2025-01-06", 1000)])

    def test_malformed_csv_header_is_a_validation_error(self):
        with self.assertRaisesRegex(ValueError, "invalid CSV"):
            read_csv("test.csv", ["header"], b'"unterminated')

    def test_inclusive_thresholds_survive_binary_rounding(self):
        self.assertTrue(Thresholds().candidate(percent(1.15, 1), None))
        self.assertTrue(Thresholds().candidate(percent(1.05, 1), percent(1.2, 1)))
        self.assertFalse(Thresholds().candidate(14.999999, 0))
        self.assertFalse(Thresholds().candidate(float("inf"), 0))


class ScopeReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = analyze(DATA_DIR / "shipment_records.csv", DATA_DIR / "context_notes.csv")

    def test_unknown_reversed_and_excluded_routes_do_not_leak_findings(self):
        for text in ["Which costs need review for Paris-Lyon in March 2025?",
                     "Which costs need review for Delhi to Mumbai in March 2025?",
                     "Which routes need review except Chennai-Bangalore in March 2025?",
                     "Which routes need review for Mumbai-Pune and Paris-Lyon in March 2025?"]:
            with self.subTest(text=text):
                self.assertEqual(answer_question(text, self.report)["findings"], [])

    def test_date_range_applies_both_boundaries(self):
        answer = answer_question("Why Chennai-Bangalore between 2025-03-03 and 2025-03-17?", self.report)
        self.assertEqual({r["week_of"] for r in answer["findings"]}, {"2025-03-03", "2025-03-10", "2025-03-17"})
        self.assertEqual(answer_question("Why Chennai-Bangalore from 2025-03-17 to 2025-03-03?", self.report)["findings"], [])

    def test_multiple_calendar_constraints_fail_closed(self):
        for text in ["Why Chennai-Bangalore in February and March 2025?",
                     "Why Chennai-Bangalore in March 2024 and 2025?",
                     "Why Chennai-Bangalore in March 2025 on 2025-04-01?"]:
            self.assertEqual(answer_question(text, self.report)["findings"], [])

    def test_abbreviated_month_and_modal_may(self):
        answer = answer_question("Why Mumbai-Pune in Sep 2025?", self.report)
        self.assertTrue(answer["findings"])
        self.assertTrue(all("2025-09" in row["week_of"] for row in answer["findings"]))
        self.assertEqual(answer_question("Which routes may need review?", self.report)["findings"],
                         answer_question("Which routes need review?", self.report)["findings"])

    def test_verdict_constraint_is_honored(self):
        self.assertEqual(answer_question("Which Chennai-Bangalore costs are unexplained in March 2025?", self.report)["findings"],
                         [{"route": "Chennai-Bangalore", "week_of": day, "flagged": "Yes", "matched_note_id": ""}
                          for day in ("2025-03-17", "2025-03-10")])
        supported = answer_question("Which routes have justified costs in January 2025?", self.report)["findings"]
        self.assertEqual([r["matched_note_id"] for r in supported], ["N002"])

    def test_shipped_question_examples_still_work(self):
        self.assertEqual(len(answer_question("Why did Chennai-Bangalore get pricier in March 2025?", self.report)["findings"]), 4)

    def test_bad_label_field_types_and_week_dates_are_rejected(self):
        labels = json.loads((ROOT / "tests/fixtures/labeled_weeks.json").read_text())
        for field, bad in [("route", []), ("week_of", "2025-01-21"), ("week_of", "2025-99-01"), ("basis", None)]:
            changed = copy.deepcopy(labels); changed[0][field] = bad
            with self.assertRaises(ValueError):
                evaluate(self.report, labels_bytes=json.dumps(changed).encode())

    def test_all_supplied_route_weeks_match_independent_decimal_calculation(self):
        result = check_numbers(DATA_DIR / "shipment_records.csv", self.report["rows"])
        self.assertEqual(result["route_weeks"], 728)
        self.assertEqual(result["field_checks"], 5096)


class ProviderEvidenceReviewTests(unittest.TestCase):
    def test_complete_quote_cannot_drop_a_leading_negation(self):
        source = "No freight cost increase was reported in the affected route."
        self.assertFalse(complete_extract(source[3:], source))
        self.assertFalse(complete_extract("freight cost increase was reported", source))
        self.assertTrue(complete_extract(source, source))
        self.assertTrue(complete_extract("Freight costs increased.", "The road flooded. Freight costs increased. Repairs started."))
        raw = json.dumps({"message": {"content": json.dumps({"note_id": "N1", "quote": source[3:]})}, "prompt_eval_count": 10, "eval_count": 10}).encode()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): return raw
        with patch("freight_watch.llm.urlopen", return_value=Response()):
            writer = QuoteWriter("model")
            self.assertEqual(writer.quote({"note_id": "N1", "text": source}), source)
            self.assertEqual(writer.log()["rejected_quotes"], 1)

    def test_nested_nonfinite_json_and_invalid_provider_ports_fail_safely(self):
        for raw in ["[" * 2000 + "0" + "]" * 2000, '{"value":NaN}', '{"value":Infinity}', '{"value":1e999}']:
            with self.assertRaises(ValueError): decode_json(raw)
        for port in ("0", "99999", "abc"):
            with self.assertRaises(ValueError): QuoteWriter("model", "http://127.0.0.1:" + port)

    def test_week_end_publication_can_describe_earlier_affected_shipments(self):
        rows = weekly_metrics([shipment("old", "A", "B", "2025-01-06", 1000),
                               shipment("new", "A", "B", "2025-01-13", 1300)])
        note = Note("N1", date(2025, 1, 17), "A-B", "A flood increased freight costs since January 13.")
        rule = {"supports_cost_increase": True, "source_sha256": note_hash(note), "effective_start": "2025-01-13", "effective_end": "2025-01-19"}
        matcher = EvidenceMatcher([note], None, NoteIndex([note]), rows, config={"notes": {"N1": rule}})
        self.assertTrue(matcher.eligibility(note, rows[-1])[0])
        future = Note("N1", date(2025, 1, 20), "A-B", note.text)
        rule["source_sha256"] = note_hash(future)
        matcher = EvidenceMatcher([future], None, NoteIndex([future]), rows, config={"notes": {"N1": rule}})
        self.assertFalse(matcher.eligibility(future, rows[-1])[0])


class ArtifactReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = temporary_directory()
        cls.folder = Path(cls.baseline.name)
        if invoke("verify", "--output-dir", str(cls.folder)) != 0:
            raise AssertionError("Cannot create reviewed test bundle.")

    @classmethod
    def tearDownClass(cls):
        cls.baseline.cleanup()

    def test_incomplete_manifest_and_truthy_nonboolean_states_are_rejected(self):
        with temporary_directory() as folder:
            target = Path(folder) / "output"; shutil.copytree(self.folder, target)
            original = json.loads((target / "run_manifest.json").read_text())
            for key, value in [("files", {}), ("evaluation_passed", "true"), ("reproducibility_passed", 1), ("strict", "true")]:
                changed = copy.deepcopy(original); changed[key] = value; write_json(target / "run_manifest.json", changed)
                with self.assertRaises(ValueError): read_bundle(target)

    def test_csv_is_read_once_into_the_verified_snapshot(self):
        real_read = Path.read_bytes
        calls = []
        def read(path):
            if path == self.folder / "output.csv": calls.append(path)
            return real_read(path)
        with patch("pathlib.Path.read_bytes", read):
            report, snapshot, _ = read_bundle(self.folder)
        self.assertEqual(len(calls), 1)
        self.assertEqual(snapshot["output.csv"], (self.folder / "output.csv").read_bytes())
        self.assertEqual(len(report["rows"]), 728)

    def test_source_fingerprints_describe_read_bytes_if_inputs_change(self):
        with temporary_directory() as folder:
            path = Path(folder) / "shipments.csv"; original = (DATA_DIR / "shipment_records.csv").read_bytes(); path.write_bytes(original)
            class ChangingWriter(QuoteWriter):
                def quote(self, note):
                    path.write_bytes(original + b"\n")
                    return super().quote(note)
            report = analyze(path, DATA_DIR / "context_notes.csv", quote_writer=ChangingWriter())
            self.assertEqual(report["summary"]["input_sha256"]["shipments"], hashlib.sha256(original).hexdigest())
            self.assertNotEqual(report["summary"]["input_sha256"]["shipments"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_cli_input_change_does_not_replace_a_previous_bundle(self):
        with temporary_directory() as folder:
            output = Path(folder) / "output"; shutil.copytree(self.folder, output)
            old_manifest = (output / "run_manifest.json").read_bytes()
            path = Path(folder) / "shipments.csv"; path.write_bytes((DATA_DIR / "shipment_records.csv").read_bytes())
            def changed(*args, **kwargs):
                report = analyze(*args, **kwargs); path.write_bytes(path.read_bytes() + b"\n"); return report
            with patch("freight_watch.__main__.analyze", side_effect=changed):
                self.assertEqual(invoke("run", "--output-dir", str(output), "--shipments", str(path)), 1)
            self.assertEqual((output / "run_manifest.json").read_bytes(), old_manifest)

    def test_cli_source_change_does_not_replace_a_previous_bundle(self):
        with temporary_directory() as folder:
            output = Path(folder) / "output"; shutil.copytree(self.folder, output)
            old = (output / "run_manifest.json").read_bytes()
            with patch("freight_watch.__main__.environment_info", side_effect=[{"source_sha256": {"a.py": "old"}}, {"source_sha256": {"a.py": "new"}}]):
                self.assertEqual(invoke("run", "--output-dir", str(output)), 1)
            self.assertEqual((output / "run_manifest.json").read_bytes(), old)

    def test_mismatched_report_and_manifest_validation_states_are_rejected(self):
        with temporary_directory() as folder:
            target = Path(folder) / "output"; shutil.copytree(self.folder, target)
            path = target / "run_manifest.json"; manifest = json.loads(path.read_text())
            report = json.loads((target / "results.json").read_text())
            report["summary"]["validation"]["strict"] = False; write_json(target / "results.json", report)
            manifest["files"]["results.json"] = hashlib.sha256((target / "results.json").read_bytes()).hexdigest()
            write_json(path, manifest)
            with self.assertRaisesRegex(ValueError, "validation states differ"): read_bundle(target)

    def project(self, root):
        for path in source_files(ROOT) + [ROOT / name for name in FILES] + [ROOT / INPUT_DIR / name for name in INPUTS]:
            target = root / path.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes() if path.exists() else b"Review document.")
        shutil.copytree(self.folder, root / "output")

    def test_package_has_verified_sources_and_excludes_unlisted_files(self):
        with temporary_directory() as folder:
            root = Path(folder); self.project(root)
            (root / "config" / ".env").write_text("private")
            target, count = build_package(root)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(count, len(archive.namelist()))
                self.assertIsNone(archive.testzip())
                self.assertNotIn("config/.env", archive.namelist())
                self.assertIn("freight_watch/bundle.py", archive.namelist())

    def test_missing_file_and_changed_source_preserve_existing_package(self):
        with temporary_directory() as folder:
            root = Path(folder); self.project(root)
            target, _ = build_package(root); original = target.read_bytes()
            path = root / "README.md"; old = path.read_bytes(); path.unlink()
            with self.assertRaises(OSError): build_package(root)
            self.assertEqual(target.read_bytes(), original); path.write_bytes(old)
            path = root / "freight_watch" / "engine.py"; path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "Source code differs"): build_package(root)
            self.assertEqual(target.read_bytes(), original)

    def test_changed_inputs_and_labels_cannot_be_packaged_with_old_evidence(self):
        with temporary_directory() as folder:
            root = Path(folder); self.project(root)
            for path, expected in [(root / INPUT_DIR / "shipment_records.csv", "inputs differ"),
                                   (root / "tests/fixtures/labeled_weeks.json", "labels differ")]:
                old = path.read_bytes(); path.write_bytes(old + b"\n")
                with self.assertRaisesRegex(ValueError, expected): build_package(root)
                path.write_bytes(old)


if __name__ == "__main__":
    unittest.main()
