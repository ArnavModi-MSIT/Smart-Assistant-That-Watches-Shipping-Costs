"""Regression and synthetic adversarial cases fixed before observing detector output."""

from contextlib import redirect_stdout, redirect_stderr
import copy
from datetime import date, timedelta
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from freight_watch.__main__ import main
from freight_watch.engine import analyze, weekly_metrics
from freight_watch.evaluation import evaluate
from freight_watch.evidence import EvidenceMatcher
from freight_watch.io import DATA_DIR, ROOT, load_notes, note_hash, write_json
from freight_watch.llm import QuoteWriter
from freight_watch.models import Note
from freight_watch.questions import answer_question
from freight_watch.retrieval import NoteIndex
from freight_watch.server import load_report
from tests.test_engine import shipment, temporary_directory


class CLIRegressionTests(unittest.TestCase):
    def invoke(self, *arguments):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(list(arguments))

    def test_bad_verify_returns_nonzero_despite_stable_results(self):
        with temporary_directory() as folder:
            result = subprocess.run([sys.executable, "-m", "freight_watch", "verify", "--output-dir", folder,
                                     "--history-threshold", "200", "--peer-threshold", "200", "--minimum-rise", "199"],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            repeat = json.loads((Path(folder) / "reproducibility.json").read_text())
            self.assertTrue(repeat["stability_passed"])
            self.assertFalse(repeat["passed"])
            self.assertIn("evaluation failed", result.stderr)
            with self.assertRaisesRegex(ValueError, "verification failed"):
                load_report(Path(folder))

    def test_exploratory_run_can_fail_labels_but_is_not_verified(self):
        with temporary_directory() as folder:
            args = ["run", "--output-dir", folder, "--history-threshold", "200", "--peer-threshold", "200", "--minimum-rise", "199"]
            self.assertEqual(self.invoke(*args), 0)
            repeat = json.loads((Path(folder) / "reproducibility.json").read_text())
            self.assertEqual(repeat["status"], "not_run")
            self.assertEqual(self.invoke(*args, "--require-evaluation-pass"), 1)

    def test_single_run_invalidates_previous_repeat_evidence(self):
        with temporary_directory() as folder:
            self.assertEqual(self.invoke("verify", "--output-dir", folder), 0)
            self.assertEqual(self.invoke("run", "--output-dir", folder), 0)
            repeat = json.loads((Path(folder) / "reproducibility.json").read_text())
            self.assertFalse(repeat["passed"])
            self.assertEqual(repeat["status"], "not_run")
            manifest = json.loads((Path(folder) / "run_manifest.json").read_text())
            self.assertNotIn("verification/run_2.csv", manifest["files"])

    def test_missing_input_leaves_existing_bundle_unchanged(self):
        with temporary_directory() as folder:
            self.assertEqual(self.invoke("verify", "--output-dir", folder), 0)
            old = (Path(folder) / "run_manifest.json").read_bytes()
            self.assertEqual(self.invoke("run", "--output-dir", folder, "--shipments", str(Path(folder) / "missing.csv")), 1)
            self.assertEqual((Path(folder) / "run_manifest.json").read_bytes(), old)

    def test_corrupt_bundle_is_rejected_by_server(self):
        with temporary_directory() as folder:
            self.assertEqual(self.invoke("verify", "--output-dir", folder), 0)
            (Path(folder) / "output.csv").write_text("corrupt", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed or is incomplete"):
                load_report(Path(folder))

    def test_output_file_cannot_be_used_as_directory(self):
        with temporary_directory() as folder:
            path = Path(folder) / "file"
            path.write_text("keep", encoding="utf-8")
            self.assertEqual(self.invoke("run", "--output-dir", str(path)), 1)
            self.assertEqual(path.read_text(), "keep")


class EvidenceAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.notes = load_notes(DATA_DIR / "context_notes.csv")
        self.rules = ROOT / "config" / "note_rules.json"

    def row(self, shipments):
        items = [shipment("history", "Chennai", "Bangalore", "2025-02-17", 1000, kind="Medium")] + shipments
        rows = weekly_metrics(items)
        return rows[-1], EvidenceMatcher(self.notes, self.rules, NoteIndex(self.notes), rows)

    def test_tiny_affected_shipment_cannot_excuse_uncovered_increase(self):
        row, matcher = self.row([shipment("affected", "Chennai", "Bangalore", "2025-03-08", 1.3, quantity=.01, kind="Medium"),
                                 shipment("uncovered", "Chennai", "Bangalore", "2025-03-09", 1298.7, quantity=9.99, kind="Medium")])
        result = matcher.assessment(self.notes[0], row)
        self.assertFalse(result["eligible"])
        self.assertAlmostEqual(result["exposure"]["affected_tonne_km_fraction"], .001)
        self.assertAlmostEqual(result["exposure"]["uncovered_rise_percent"], 29.97)

    def test_partly_affected_week_with_normal_uncovered_shipments_can_pass(self):
        row, matcher = self.row([shipment("affected", "Chennai", "Bangalore", "2025-03-08", 1170, quantity=9, kind="Medium"),
                                 shipment("uncovered", "Chennai", "Bangalore", "2025-03-09", 100, quantity=1, kind="Medium")])
        result = matcher.assessment(self.notes[0], row)
        self.assertTrue(result["eligible"])
        self.assertAlmostEqual(result["exposure"]["uncovered_rise_percent"], 0)

    def test_date_list_without_amounts_is_insufficient(self):
        row, matcher = self.row([shipment("1", "Chennai", "Bangalore", "2025-03-08", 1300, kind="Medium")])
        row.pop("daily_totals")
        self.assertFalse(matcher.eligibility(self.notes[0], row)[0])

    def test_unreviewed_note_fails_closed(self):
        unknown = Note("NEW", date(2025, 3, 3), "Chennai-Bangalore", "Flooding increased transport costs this week.")
        notes = self.notes + [unknown]
        matcher = EvidenceMatcher(notes, self.rules, NoteIndex(notes))
        row, _ = self.row([shipment("1", "Chennai", "Bangalore", "2025-03-08", 1300, kind="Medium")])
        self.assertIn("Unreviewed", matcher.eligibility(unknown, row)[1])

    def test_multiple_matches_are_ranked_and_all_recorded(self):
        duplicate = Note("N011", self.notes[0].day, self.notes[0].applies_to, self.notes[0].text)
        notes = self.notes + [duplicate]
        rules = json.loads(self.rules.read_text())
        rules["notes"]["N011"] = dict(rules["notes"]["N001"], source_sha256=note_hash(duplicate))
        row, _ = self.row([shipment("1", "Chennai", "Bangalore", "2025-03-08", 1300, kind="Medium")])
        with temporary_directory() as folder:
            path = Path(folder) / "rules.json"; write_json(path, rules)
            matcher = EvidenceMatcher(notes, path, NoteIndex(notes))
            matched, retrieved = matcher.match(row)
        self.assertEqual(matched["note_id"], "N001")
        self.assertEqual({n["note_id"] for n in retrieved if n["eligible"]}, {"N001", "N011"})

    def test_midweek_fuel_dilution_uses_tonne_km_exposure(self):
        items = [shipment("before", "Mumbai", "Pune", "2025-05-05", 1000),
                 shipment("after", "Mumbai", "Pune", "2025-05-08", 1000),
                 shipment("current", "Mumbai", "Pune", "2025-05-12", 1060)]
        rows = weekly_metrics(items)
        rules = json.loads(self.rules.read_text()); rules["notes"]["N003"]["effective_start"] = "2025-05-07"
        with temporary_directory() as folder:
            path = Path(folder) / "rules.json"; write_json(path, rules)
            matcher = EvidenceMatcher(self.notes, path, NoteIndex(self.notes), rows)
            allowed, reason = matcher.eligibility(self.notes[2], rows[-1])
        self.assertFalse(allowed)
        self.assertIn("allowance 5.5%", reason)


class QueryAndEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = analyze(DATA_DIR / "shipment_records.csv", DATA_DIR / "context_notes.csv")

    def test_march_includes_the_february_boundary_week(self):
        answer = answer_question("Why Chennai to Bangalore in March 2025?", self.report)
        self.assertIn("2025-02-24", answer["answer"])
        self.assertEqual(len(answer["findings"]), 4)

    def test_january_includes_previous_year_week(self):
        report = copy.deepcopy(self.report)
        report["rows"] = [r for r in report["rows"] if r["route"] == "Mumbai-Pune" and r["week_of"] == "2024-12-30"]
        answer = answer_question("Why Mumbai to Pune in January 2025?", report)
        self.assertIn("2024-12-30", answer["answer"])

    def test_leap_day_week_is_included_in_february(self):
        report = copy.deepcopy(self.report)
        report["rows"] = [r for r in report["rows"] if r["route"] == "Mumbai-Pune" and r["week_of"] == "2024-02-26"]
        self.assertIn("2024-02-26", answer_question("Why Mumbai-Pune in February 2024?", report)["answer"])

    def test_empty_label_set_fails_instead_of_dividing_by_zero(self):
        with temporary_directory() as folder:
            path = Path(folder) / "labels.json"; path.write_text("[]")
            with self.assertRaisesRegex(ValueError, "nonempty"):
                evaluate(self.report, path)

    def test_citation_check_does_not_trust_stored_eligible_boolean(self):
        report = copy.deepcopy(self.report)
        row = next(r for r in report["rows"] if r["matched_note_id"] == "N001")
        row["matched_note_id"] = "N006"
        for ref in row["retrieved_notes"]:
            ref["eligible"] = True
        self.assertFalse(evaluate(report)["all_justified_rows_have_eligible_citations"])

    def test_retrieval_empty_and_unknown_query_are_deterministic(self):
        self.assertEqual(NoteIndex([]).search("anything"), [])
        notes = load_notes(DATA_DIR / "context_notes.csv")
        ranking = NoteIndex(list(reversed(notes))).search("zzzzzz")
        self.assertEqual([n.note_id for n, score in ranking], sorted(n.note_id for n in notes))
        self.assertTrue(all(score == 0 for n, score in ranking))

    def test_matching_route_scores_above_unrelated_route(self):
        notes = load_notes(DATA_DIR / "context_notes.csv")
        scores = {n.note_id: score for n, score in NoteIndex(notes).search("Chennai Bangalore flooding")}
        self.assertGreater(scores["N001"], scores["N002"])


class ProviderResilienceTests(unittest.TestCase):
    def test_bad_response_shapes_and_token_types_fail_safely(self):
        note = {"note_id": "N001", "text": "Flooding increased the cost of transport."}
        for payload in [[], None, {"message": None}, {"message": {"content": "bad JSON"}},
                        {"prompt_eval_count": "100", "eval_count": -10, "message": {"content": json.dumps({"note_id": "N001", "quote": note["text"]})}}]:
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, *args): return json.dumps(payload).encode()
            with patch("freight_watch.llm.urlopen", return_value=Response()):
                writer = QuoteWriter("local-model")
                self.assertEqual(writer.quote(note), note["text"])
                self.assertIsNone(writer.log()["input_tokens"])
                self.assertGreaterEqual(writer.calls[0]["duration_seconds"], 0)

    def test_endpoint_credentials_and_invalid_timeout_are_rejected(self):
        for url in ["http://user:password@127.0.0.1:11434", "http://127.0.0.1:11434/path", "http://127.0.0.1:11434?secret=x"]:
            with self.assertRaises(ValueError): QuoteWriter("model", url)
        for timeout in [0, -1, float("nan")]:
            with self.assertRaises(ValueError): QuoteWriter("model", timeout=timeout)
