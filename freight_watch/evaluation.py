"""Small explicitly labeled set; thresholds are judgment, not hidden ground truth."""

from .io import ROOT, decode_json
from .models import Note
from .models import Thresholds
from .evidence import EvidenceMatcher
from .retrieval import NoteIndex
from datetime import date


def evaluate(report, fixture_path=None, rules_path=None, labels_bytes=None):
    path = fixture_path or ROOT / "tests" / "fixtures" / "labeled_weeks.json"
    labels = decode_json(path.read_bytes() if labels_bytes is None else labels_bytes, "Reference labels")
    if not isinstance(labels, list) or not labels:
        raise ValueError("Reference evaluation requires a nonempty list of labels.")
    if any(not isinstance(label, dict) or not all(k in label for k in ("route", "week_of", "flagged", "matched_note_id", "basis")) for label in labels):
        raise ValueError("Invalid reference label schema.")
    fields = ("route", "week_of", "flagged", "matched_note_id", "basis")
    if any(not all(isinstance(label[k], str) for k in fields) or not label["route"].strip()
           or not label["basis"].strip() for label in labels):
        raise ValueError("Reference label fields must be strings with a route and explanation.")
    for label in labels:
        try:
            week = date.fromisoformat(label["week_of"])
        except ValueError as exc:
            raise ValueError("Reference week must be a Monday date in YYYY-MM-DD format.") from exc
        if week.weekday() != 0 or week.isoformat() != label["week_of"]:
            raise ValueError("Reference week must be a Monday date in YYYY-MM-DD format.")
    if len({(l["route"], l["week_of"]) for l in labels}) != len(labels):
        raise ValueError("Duplicate reference label.")
    if any(l["flagged"] not in ("Yes", "No", "No (justified)") or not isinstance(l["matched_note_id"], str)
           or (l["flagged"] == "No (justified)") != bool(l["matched_note_id"]) for l in labels):
        raise ValueError("Invalid reference verdict or note-ID convention.")
    lookup = {(r["route"], r["week_of"]): r for r in report["rows"]}
    checks = []
    for label in labels:
        row = lookup.get((label["route"], label["week_of"]))
        actual = {"flagged": row["flagged"], "matched_note_id": row["matched_note_id"]} if row else None
        expected = {"flagged": label["flagged"], "matched_note_id": label["matched_note_id"]}
        checks.append({"route": label["route"], "week_of": label["week_of"],
                       "expected": expected, "actual": actual, "passed": actual == expected,
                       "label_basis": label["basis"]})
    supported = [r for r in report["rows"] if r["matched_note_id"]]
    notes = [Note(n["note_id"], date.fromisoformat(n["date"]), n["applies_to"], n["text"]) for n in report["notes"]]
    matcher = EvidenceMatcher(notes, rules_path or ROOT / "config" / "note_rules.json", NoteIndex(notes), report["rows"])
    citations_valid = all(r["flagged"] == "No (justified)" and r["matched_note_id"] in matcher.notes
                          and matcher.eligibility(matcher.notes[r["matched_note_id"]], r)[0] for r in supported)
    citations_valid = citations_valid and all(r.get("matched_note_id") for r in report["rows"] if r["flagged"] == "No (justified)")
    confusion = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for check in checks:
        expected_positive = check["expected"]["flagged"] == "Yes"
        if check["actual"] is None:
            continue
        actual_positive = check["actual"]["flagged"] == "Yes"
        confusion["tp" if expected_positive and actual_positive else "fn" if expected_positive else "fp" if actual_positive else "tn"] += 1
    return {"label_count": len(checks), "passed": sum(c["passed"] for c in checks),
            "accuracy_on_this_small_set": sum(c["passed"] for c in checks) / len(checks),
            "label_method": "Human-authored reference cases from sample examples, event windows and stable weeks; not a complete ground-truth dataset.",
            "unexplained_confusion_on_reference_set": confusion,
            "all_justified_rows_have_eligible_citations": citations_valid, "checks": checks}


def threshold_sensitivity(report):
    """Nine transparent counterfactual configurations; no new ground-truth labels."""
    scenarios = []
    for history in (10, 15, 20):
        for peer in (15, 20, 25):
            rule = Thresholds(history, peer, 5)
            selected = [r for r in report["rows"] if rule.candidate(r["history_change_percent"], r["peer_change_percent"])]
            justified = sum(bool(r["eligible_note_ids"]) for r in selected)
            scenarios.append({"history_threshold": history, "peer_threshold": peer, "minimum_rise": 5,
                              "candidates": len(selected), "justified": justified, "unexplained": len(selected) - justified})
    return {"purpose": "Sensitivity counts only; no estimate of precision/recall or threshold calibration.",
            "input_sha256": report["summary"]["input_sha256"], "scenarios": scenarios}
