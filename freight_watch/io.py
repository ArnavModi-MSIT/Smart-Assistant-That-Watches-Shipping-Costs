"""Strict input validation. Never repair or overwrite supplied source files."""

import csv
import hashlib
import json
import math
import io
from datetime import date
from pathlib import Path

from .models import Note, Shipment

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "AI Intern Case Study" / "AI Intern Case Study"
OUTPUT_COLUMNS = [
    "route", "week_of", "cost_per_tonne_km", "vs_own_history",
    "vs_similar_routes", "flagged", "matched_note_id", "reason",
]


def read_csv(path, columns, source_bytes=None):
    raw = Path(path).read_bytes() if source_bytes is None else source_bytes
    with io.StringIO(raw.decode("utf-8-sig"), newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        try:
            if reader.fieldnames != columns:
                raise ValueError(f"{Path(path).name}: unexpected CSV column names or order.")
            rows = list(reader)
        except csv.Error as exc:
            raise ValueError(f"{Path(path).name}: invalid CSV near line {reader.line_num}: {exc}") from exc
    for index, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{Path(path).name}: row {index} has the wrong field count.")
        if any(not value.strip() for value in row.values()):
            raise ValueError(f"{Path(path).name}: row {index} has a missing value.")
    if not rows:
        raise ValueError(f"{Path(path).name}: empty input.")
    return rows


def load_shipments(path, source_bytes=None):
    columns = ["shipment_id", "origin", "destination", "route_type", "material",
               "quantity_tonnes", "distance_km", "freight_cost_inr",
               "shipment_date", "transporter"]
    result, seen, types, labels = [], set(), {}, {}
    for line, row in enumerate(read_csv(path, columns, source_bytes), 2):
        if row["shipment_id"] in seen:
            raise ValueError(f"Duplicate shipment ID at row {line}.")
        seen.add(row["shipment_id"])
        if row["route_type"] not in {"Short", "Medium", "Long"}:
            raise ValueError(f"Unknown route_type at row {line}.")
        try:
            values = [float(row[c]) for c in ("quantity_tonnes", "distance_km", "freight_cost_inr")]
            day = date.fromisoformat(row["shipment_date"])
        except ValueError as exc:
            raise ValueError(f"{Path(path).name}: invalid numeric value or date at row {line}: {exc}") from exc
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError(f"Invalid quantity, distance or cost at row {line}.")
        work = values[0] * values[1]
        if not math.isfinite(work) or work <= 0:
            raise ValueError(f"Shipment tonne-km is outside supported numeric range at row {line}.")
        item = Shipment(row["shipment_id"], row["origin"], row["destination"],
                        row["route_type"], *values, day)
        if item.route in types and types[item.route] != item.route_type:
            raise ValueError(f"Route {item.route} has conflicting route_type values.")
        pair = (item.origin, item.destination)
        if item.route in labels and labels[item.route] != pair:
            raise ValueError(f"Ambiguous route label {item.route}; origin/destination pairs must be distinct.")
        types[item.route] = item.route_type
        labels[item.route] = pair
        result.append(item)
    return result


def load_notes(path, source_bytes=None):
    rows = read_csv(path, ["note_id", "date", "applies_to", "note"], source_bytes)
    notes = []
    for line, row in enumerate(rows, 2):
        try:
            day = date.fromisoformat(row["date"])
        except ValueError as exc:
            raise ValueError(f"{Path(path).name}: invalid note date at row {line}: {exc}") from exc
        notes.append(Note(row["note_id"], day, row["applies_to"], row["note"]))
    if len({n.note_id for n in notes}) != len(notes):
        raise ValueError("Duplicate note ID.")
    return notes


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode_json(raw, context="JSON"):
    def reject_constant(value):
        raise ValueError(f"Nonfinite literal {value} is not valid JSON.")
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("JSON number exceeds supported numeric range.")
        return result
    try:
        return json.loads(raw, parse_constant=reject_constant, parse_float=finite_float)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"{context}: invalid or excessively nested JSON: {exc}") from exc


def note_hash(note):
    raw = json.dumps([note.day.isoformat(), note.applies_to, note.text], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_output(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
