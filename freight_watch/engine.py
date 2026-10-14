from collections import defaultdict, deque
from dataclasses import asdict
from datetime import date, timedelta
import math
import hashlib
from pathlib import Path

from .evidence import EvidenceMatcher
from .io import ROOT, decode_json, load_notes, load_shipments
from .llm import QuoteWriter
from .models import Thresholds
from .retrieval import NoteIndex


def monday(day):
    return day - timedelta(days=day.weekday())


def percent(value, baseline):
    if baseline is None or baseline <= 0:
        return None
    result = (value / baseline - 1) * 100
    if not math.isfinite(result):
        raise ValueError("Comparison exceeds supported numeric range.")
    return result


def finite_sum(values):
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ValueError("Shipment totals exceed supported numeric range.") from exc
    if not math.isfinite(result):
        raise ValueError("Shipment totals exceed supported numeric range.")
    return result


def mean(values):
    if not values:
        return None
    try:
        return math.fsum(values) / len(values)
    except OverflowError:
        return finite_sum(value / len(values) for value in values)


def weekly_metrics(shipments):
    grouped = defaultdict(list)
    labels = {}
    for shipment in shipments:
        pair = (shipment.origin, shipment.destination)
        if shipment.route in labels and labels[shipment.route] != pair:
            raise ValueError("Ambiguous directional route label.")
        labels[shipment.route] = pair
        work = shipment.quantity * shipment.distance
        if not math.isfinite(work) or work <= 0:
            raise ValueError("Shipment tonne-km is outside supported numeric range.")
        grouped[(shipment.route, shipment.route_type, monday(shipment.day))].append(shipment)
    rows = []
    for (route, kind, week), items in sorted(grouped.items()):
        items = sorted(items, key=lambda item: item.shipment_id)
        cost = finite_sum(item.cost for item in items)
        work = finite_sum(item.quantity * item.distance for item in items)
        rate = cost / work
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Weekly freight rate is outside supported numeric range.")
        by_day = defaultdict(list)
        for item in items:
            by_day[item.day.isoformat()].append(item)
        daily = [{"date": day, "cost_inr": math.fsum(i.cost for i in group),
                  "tonne_km": math.fsum(i.quantity * i.distance for i in group),
                  "shipments": len(group)} for day, group in sorted(by_day.items())]
        rows.append({"route": route, "origin": items[0].origin, "destination": items[0].destination,
                     "route_type": kind, "week_of": week.isoformat(),
                     "cost_per_tonne_km": rate, "total_cost_inr": cost,
                     "total_tonne_km": work, "shipment_count": len(items),
                     "shipment_dates": sorted(by_day), "daily_totals": daily})
    peers = defaultdict(list)
    for row in rows:
        peers[(row["route_type"], row["week_of"])].append(row)
    windows = defaultdict(deque)
    for row in rows:
        week = date.fromisoformat(row["week_of"])
        start = date.fromordinal(max(1, week.toordinal() - 56)).isoformat()
        history = windows[(row["route"], row["route_type"])]
        while history and history[0]["week_of"] < start:
            history.popleft()
        others = [r for r in peers[(row["route_type"], row["week_of"])] if r["route"] != row["route"]]
        history_average = mean([r["cost_per_tonne_km"] for r in history])
        peer_average = mean([r["cost_per_tonne_km"] for r in others])
        row.update(history_weeks=[r["week_of"] for r in history], history_week_count=len(history),
                   history_average=history_average, peer_average=peer_average, peer_count=len(others),
                   history_change_percent=percent(row["cost_per_tonne_km"], history_average),
                   peer_change_percent=percent(row["cost_per_tonne_km"], peer_average))
        history.append(row)
    return rows


def format_comparison(value, description):
    if value is not None:
        return f"{value:+.1f}% vs {description}"
    missing = "prior route history" if description.startswith("this route") else "similar routes this week"
    return f"N/A (no {missing})"


def output_row(row):
    return {"route": row["route"], "week_of": row["week_of"],
            "cost_per_tonne_km": f"{row['cost_per_tonne_km']:.2f}",
            "vs_own_history": format_comparison(row["history_change_percent"], "this route's past average"),
            "vs_similar_routes": format_comparison(row["peer_change_percent"], "similar-length routes this week"),
            "flagged": row["flagged"], "matched_note_id": row["matched_note_id"], "reason": row["reason"]}


def analyze(shipments_path, notes_path, thresholds=None, quote_writer=None, rules_path=None):
    thresholds = thresholds or Thresholds()
    quote_writer = quote_writer or QuoteWriter()
    rules_path = rules_path or ROOT / "config" / "note_rules.json"
    raw_sources = {"shipments": Path(shipments_path).read_bytes(), "notes": Path(notes_path).read_bytes(),
                   "note_rules": Path(rules_path).read_bytes()}
    shipments, notes = load_shipments(shipments_path, raw_sources["shipments"]), load_notes(notes_path, raw_sources["notes"])
    rules_config = decode_json(raw_sources["note_rules"], "Note rules")
    rows = weekly_metrics(shipments)
    index = NoteIndex(notes)
    matcher = EvidenceMatcher(notes, rules_path, index, rows, config=rules_config)
    for row in rows:
        candidate = thresholds.candidate(row["history_change_percent"], row["peer_change_percent"])
        matched, inspected = matcher.match(row)
        row["candidate"] = candidate
        row["retrieved_notes"] = inspected
        row["eligible_note_ids"] = [n["note_id"] for n in inspected if n["eligible"]]
        row["matched_note_id"] = matched["note_id"] if candidate and matched else ""
        history_count = row["history_week_count"]
        coverage = f"History uses {history_count} prior observed week(s) within the preceding 8 calendar weeks."
        if not candidate:
            row["flagged"] = "No"
            row["reason"] = ("Insufficient history to establish a rise. " if history_count == 0
                             else "No unusual rise under the configured thresholds. ") + coverage
        elif matched:
            row["flagged"] = "No (justified)"
            quote = quote_writer.quote(matched)
            rule = matcher.rules[matched["note_id"]]
            end = rule.get("effective_end") or "onward"
            row["reason"] = (f"Justified by note {matched['note_id']} dated {matched['date']}: {quote} "
                             f"Applicable window: {rule['effective_start']} to {end}. {coverage}")
        else:
            row["flagged"] = "Yes"
            row["reason"] = "Unexplained cost rise: no note supports this route, shipment dates and increase. " + coverage
            relevant = next((n for n in inspected if matcher.notes[n["note_id"]].applies_to in (row["route"], "All Routes")), None)
            if relevant:
                row["reason"] += f" Note {relevant['note_id']} was rejected: {relevant['check']}"
        if matched and candidate and matched.get("exposure", {}).get("affected_tonne_km_fraction", 1) < 1:
            exposure = matched["exposure"]
            row["reason"] += (f" Partial event exposure: {exposure['affected_tonne_km_fraction']:.1%} of tonne-km; "
                              f"uncovered shipments contribute {exposure['uncovered_rise_percent']:.1f} percentage points "
                              "of weekly rise. This is note support, not full causal attribution.")
    csv_rows = [output_row(row) for row in rows]
    days = [shipment.day.isoformat() for shipment in shipments]
    log = quote_writer.log()
    summary = {"shipments": len(shipments), "routes": len({r["route"] for r in rows}),
               "weeks": len({r["week_of"] for r in rows}), "route_weeks": len(rows),
               "date_start": min(days), "date_end": max(days),
               "candidates": sum(r["candidate"] for r in rows),
               "unexplained": sum(r["flagged"] == "Yes" for r in rows),
               "justified": sum(r["flagged"] == "No (justified)" for r in rows),
               "thresholds": asdict(thresholds), "llm_model": quote_writer.model,
               "ai_status": {k: log[k] for k in ("model_attempted", "calls_failed", "rejected_quotes", "source_quote_fallbacks", "accepted_quotes")},
               "baseline_method": "Arithmetic mean of prior 8 calendar-week route rates; arithmetic mean of other same-week routes of the supplied type.",
               "input_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in raw_sources.items()}}
    return {"summary": summary, "rows": rows, "csv_rows": csv_rows, "evidence_rules": rules_config,
            "notes": [{"note_id": n.note_id, "date": n.day.isoformat(), "applies_to": n.applies_to, "text": n.text} for n in notes],
            "token_cost_log": log}
