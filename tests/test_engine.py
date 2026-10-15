from datetime import date
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from freight_watch.engine import analyze, monday, weekly_metrics
from freight_watch.evidence import EvidenceMatcher
from freight_watch.evaluation import evaluate
from freight_watch.io import DATA_DIR, ROOT, OUTPUT_COLUMNS, load_notes, load_shipments, write_output
from freight_watch.llm import QuoteWriter
from freight_watch.models import Shipment, Thresholds
from freight_watch.questions import answer_question
from freight_watch.retrieval import NoteIndex


def shipment(identifier, origin, destination, day, cost, quantity=10, distance=100, kind="Short"):
    return Shipment(identifier, origin, destination, kind, quantity, distance, cost, date.fromisoformat(day))


def temporary_directory():
    parent = (ROOT / "tmp" / "tests").resolve()
    if not parent.is_relative_to(ROOT.resolve()):
        raise ValueError("Test directory escaped the workspace.")
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


class WeeklyMathTests(unittest.TestCase):
    def test_weighted_weekly_ratio_and_monday_sunday_boundaries(self):
        rows = weekly_metrics([
            shipment("1", "A", "B", "2025-01-06", 1000),
            shipment("2", "A", "B", "2025-01-12", 4000, quantity=20),
            shipment("3", "A", "B", "2025-01-13", 1500),
        ])
        self.assertAlmostEqual(rows[0]["cost_per_tonne_km"], 5000 / 3000)
        self.assertEqual(rows[0]["shipment_count"], 2)
        self.assertEqual(rows[1]["week_of"], "2025-01-13")

    def test_current_and_future_weeks_never_enter_history(self):
        rows = weekly_metrics([shipment(str(i), "A", "B", f"2025-01-{day:02d}", cost)
                               for i, (day, cost) in enumerate([(6, 1000), (13, 2000), (20, 90000)])])
        self.assertEqual(rows[0]["history_average"], None)
        self.assertEqual(rows[1]["history_average"], 1.0)
        self.assertEqual(rows[2]["history_average"], 1.5)

    def test_eight_calendar_weeks_do_not_pull_in_stale_observations(self):
        rows = weekly_metrics([shipment("1", "A", "B", "2024-01-01", 999000),
                               shipment("2", "A", "B", "2025-01-06", 2000),
                               shipment("3", "A", "B", "2025-03-03", 3000),
                               shipment("4", "A", "B", "2025-03-10", 4000)])
        self.assertEqual(rows[2]["history_week_count"], 1)
        self.assertEqual(rows[2]["history_average"], 2.0)
        self.assertEqual(rows[3]["history_average"], 3.0)

    def test_peer_average_is_equal_weighted_and_excludes_route(self):
        rows = weekly_metrics([shipment("1", "A", "B", "2025-01-06", 1000),
                               shipment("2", "C", "D", "2025-01-06", 3000),
                               shipment("3", "E", "F", "2025-01-06", 5000, kind="Long")])
        self.assertEqual(rows[0]["peer_average"], 3.0)
        self.assertEqual(rows[1]["peer_average"], 1.0)
        self.assertIsNone(rows[2]["peer_average"])

    def test_first_week_and_configurable_thresholds(self):
        rule = Thresholds()
        self.assertFalse(rule.candidate(None, 50))
        self.assertFalse(rule.candidate(-5, 50))
        self.assertFalse(rule.candidate(4.9, 50))
        self.assertTrue(rule.candidate(5, 20))
        self.assertTrue(rule.candidate(15, None))
        with self.assertRaises(ValueError):
            Thresholds(float("nan"), 20, 5)

    def test_input_order_does_not_change_results(self):
        items = [shipment(str(i), "A", "B", "2025-01-06", c) for i, c in enumerate([1000, 3333, 7777])]
        self.assertEqual(weekly_metrics(items), weekly_metrics(list(reversed(items))))


class ProvidedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = analyze(DATA_DIR / "shipment_records.csv", DATA_DIR / "context_notes.csv")
        cls.lookup = {(r["route"], r["week_of"]): r for r in cls.report["rows"]}
        cls.notes = load_notes(DATA_DIR / "context_notes.csv")
        cls.matcher = EvidenceMatcher(cls.notes, ROOT / "config" / "note_rules.json", NoteIndex(cls.notes))

    def test_three_sample_numeric_examples(self):
        expectations = [("Delhi-Jaipur", "2024-11-11", "4.17", "+35.5%", "+21.0%"),
                        ("Ahmedabad-Mumbai", "2025-01-20", "3.29", "+29.5%", "+22.5%"),
                        ("Mumbai-Pune", "2025-09-15", "3.98", "+9.2%", "+23.6%")]
        csv_lookup = {(r["route"], r["week_of"]): r for r in self.report["csv_rows"]}
        for route, week, cost, history, peer in expectations:
            row = csv_lookup[(route, week)]
            self.assertEqual(row["cost_per_tonne_km"], cost)
            self.assertTrue(row["vs_own_history"].startswith(history))
            self.assertTrue(row["vs_similar_routes"].startswith(peer))

    def test_labeled_reference_cases(self):
        check = evaluate(self.report)
        self.assertEqual(check["passed"], check["label_count"])
        self.assertTrue(check["all_justified_rows_have_eligible_citations"])

    def test_expired_flood_is_not_justification(self):
        before = self.lookup[("Chennai-Bangalore", "2025-03-03")]
        after = self.lookup[("Chennai-Bangalore", "2025-03-10")]
        self.assertEqual(before["matched_note_id"], "N001")
        self.assertEqual(after["flagged"], "Yes")
        self.assertEqual(after["matched_note_id"], "")

    def test_rejection_explains_known_event_instead_of_future_distractor(self):
        flood = self.lookup[("Chennai-Bangalore", "2025-03-10")]["reason"]
        self.assertIn("Note N001 was rejected", flood)
        self.assertIn("2025-02-24 to 2025-03-08", flood)
        self.assertNotIn("N009", flood)
        drift = self.lookup[("Mumbai-Pune", "2025-09-15")]["reason"]
        self.assertIn("Note N003 was rejected", drift)
        self.assertIn("already included throughout the historical baseline", drift)
        self.assertNotIn("N006", drift)

    def test_route_and_publication_filters(self):
        row = self.lookup[("Mumbai-Pune", "2025-09-15")]
        flood = self.notes[0]
        future = next(n for n in self.notes if n.note_id == "N006")
        self.assertFalse(self.matcher.eligibility(flood, row)[0])
        self.assertIn("published after", self.matcher.eligibility(future, row)[1])

    def test_global_fuel_note_cannot_excuse_late_drift(self):
        row = self.lookup[("Mumbai-Pune", "2025-09-15")]
        fuel = next(n for n in self.notes if n.note_id == "N003")
        allowed, reason = self.matcher.eligibility(fuel, row)
        self.assertFalse(allowed)
        self.assertIn("baseline", reason)

    def test_nonimpact_notes_are_rejected_even_with_scope_and_time(self):
        for note_id, route, week in [("N004", "Delhi-Jaipur", "2024-03-11"),
                                    ("N005", "Mumbai-Delhi", "2024-07-29"),
                                    ("N010", "Delhi-Chennai", "2025-10-27")]:
            note = next(n for n in self.notes if n.note_id == note_id)
            self.assertFalse(self.matcher.eligibility(note, self.lookup[(route, week)])[0])

    def test_large_uplift_is_not_explained_by_small_fuel_change(self):
        row = dict(self.lookup[("Mumbai-Pune", "2025-05-05")])
        row["history_change_percent"] = 30
        fuel = next(n for n in self.notes if n.note_id == "N003")
        self.assertIn("exceeds", self.matcher.eligibility(fuel, row)[1])

    def test_fuel_note_has_valid_start_week_evidence(self):
        row = dict(self.lookup[("Mumbai-Pune", "2025-05-05")])
        row["history_change_percent"] = 6.0
        fuel = next(n for n in self.notes if n.note_id == "N003")
        self.assertTrue(self.matcher.eligibility(fuel, row)[0])

    def test_only_affected_shipment_dates_count(self):
        row = dict(self.lookup[("Chennai-Bangalore", "2025-03-03")])
        row["shipment_dates"] = ["2025-03-09"]
        row["daily_totals"] = [{"date": "2025-03-09", "cost_inr": row["total_cost_inr"], "tonne_km": row["total_tonne_km"], "shipments": row["shipment_count"]}]
        self.assertFalse(self.matcher.eligibility(self.notes[0], row)[0])

    def test_all_justified_rows_have_source_grounded_reasons(self):
        notes = {n.note_id: n for n in self.notes}
        for row in self.report["rows"]:
            if row["matched_note_id"]:
                self.assertEqual(row["flagged"], "No (justified)")
                self.assertIn(notes[row["matched_note_id"]].text, row["reason"])
            else:
                self.assertNotEqual(row["flagged"], "No (justified)")

    def test_output_csv_roundtrips_with_exact_contract(self):
        with temporary_directory() as temp:
            path = Path(temp) / "result.csv"
            write_output(path, self.report["csv_rows"])
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(reader.fieldnames, OUTPUT_COLUMNS)
                self.assertEqual(list(reader), self.report["csv_rows"])

    def test_question_date_and_ambiguity_handling(self):
        answer = answer_question("Why Chennai-Bangalore in March 2025?", self.report)
        self.assertIn("2025-03-10", answer["answer"])
        self.assertIn("year", answer_question("Why Chennai-Bangalore in March?", self.report)["answer"])
        self.assertIn("invalid", answer_question("Why Mumbai-Pune on 2025-99-01?", self.report)["answer"])
        self.assertIn("ends on", answer_question("What is happening today?", self.report)["answer"])


class LLMGuardTests(unittest.TestCase):
    def test_offline_mode_has_zero_calls_and_no_invented_tokens(self):
        writer = QuoteWriter()
        self.assertEqual(writer.log()["llm_calls"], 0)
        self.assertEqual(writer.log()["input_tokens"], 0)

    def test_failed_call_tokens_remain_unknown(self):
        with patch("freight_watch.llm.urlopen", side_effect=URLError("offline")):
            writer = QuoteWriter("local-model")
            text = writer.quote({"note_id": "N001", "text": "Flooding increased the cost of transport."})
        self.assertEqual(text, "Flooding increased the cost of transport.")
        self.assertIsNone(writer.log()["input_tokens"])
        self.assertEqual(writer.log()["llm_calls"], 1)

    def test_fabricated_quote_and_wrong_note_are_rejected(self):
        note = {"note_id": "N001", "text": "Flooding increased the cost of transport."}
        for selection in [{"note_id": "N001", "quote": "Fuel prices rose by thirty percent."},
                          {"note_id": "N002", "quote": note["text"]}, []]:
            payload = {"prompt_eval_count": 100, "eval_count": 20, "message": {"content": json.dumps(selection)}}
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, *args): return json.dumps(payload).encode()
            with patch("freight_watch.llm.urlopen", return_value=Response()):
                writer = QuoteWriter("local-model")
                self.assertEqual(writer.quote(note), note["text"])
                self.assertFalse(writer.calls[0]["accepted"])
                writer.quote(note)
                self.assertEqual(len(writer.calls), 1)

    def test_valid_exact_quote_is_accepted_and_tokens_are_logged(self):
        note = {"note_id": "N001", "text": "Flooding increased the cost of transport. Roads recovered later."}
        payload = {"prompt_eval_count": 120, "eval_count": 25,
                   "message": {"content": json.dumps({"note_id": "N001", "quote": "Flooding increased the cost of transport."})}}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *args): return json.dumps(payload).encode()
        with patch("freight_watch.llm.urlopen", return_value=Response()):
            writer = QuoteWriter("local-model")
            writer.quote(note)
        self.assertEqual(writer.log()["accepted_quotes"], 1)
        self.assertEqual(writer.log()["input_tokens"], 120)

    def test_remote_endpoint_is_not_used(self):
        with self.assertRaises(ValueError):
            QuoteWriter("local-model", "https://example.com")


class InputValidationTests(unittest.TestCase):
    def test_missing_nonfinite_duplicate_and_malformed_inputs_fail(self):
        lines = (DATA_DIR / "shipment_records.csv").read_text(encoding="utf-8").splitlines()
        original = lines[1].split(",")
        cases = []
        for value in ["", "0", "-1", "nan", "inf"]:
            row = original.copy(); row[5] = value
            cases.append([",".join(row)])
        cases.extend([[lines[1], lines[1]], [lines[1] + ",extra"]])
        with temporary_directory() as temp:
            path = Path(temp) / "input.csv"
            for rows in cases:
                path.write_text(lines[0] + "\n" + "\n".join(rows), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_shipments(path)

    def test_changed_note_requires_annotation_review(self):
        notes = load_notes(DATA_DIR / "context_notes.csv")
        changed = type(notes[0])(notes[0].note_id, notes[0].day, notes[0].applies_to, "Changed flood dates.")
        with self.assertRaises(ValueError):
            EvidenceMatcher([changed], ROOT / "config" / "note_rules.json", NoteIndex([changed]))


if __name__ == "__main__":
    unittest.main()
