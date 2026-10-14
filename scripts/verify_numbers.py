"""Independent Decimal reconstruction; does not reuse the engine's calculations."""

import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from freight_watch.bundle import read_bundle


def check_numbers(shipments_path, rows):
    with localcontext() as context:
        context.prec = 50
        groups = {}
        with Path(shipments_path).open(encoding="utf-8-sig", newline="") as stream:
            for source in csv.DictReader(stream):
                day = date.fromisoformat(source["shipment_date"])
                week = day - timedelta(days=day.weekday())
                key = (source["origin"], source["destination"], source["route_type"], week)
                cost, work, count = groups.get(key, (Decimal(0), Decimal(0), 0))
                groups[key] = (cost + Decimal(source["freight_cost_inr"]),
                               work + Decimal(source["quantity_tonnes"]) * Decimal(source["distance_km"]), count + 1)
        rates = {key: cost / work for key, (cost, work, count) in groups.items()}
        observed = {(r["origin"], r["destination"], r["route_type"], date.fromisoformat(r["week_of"])): r for r in rows}
        if len(observed) != len(rows) or set(observed) != set(groups):
            raise ValueError("Route-week identities differ from the source reconstruction.")
        largest = Decimal(0)
        comparisons = 0
        for key, rate in rates.items():
            history = [value for other, value in rates.items() if other[:3] == key[:3] and 0 < (key[3] - other[3]).days <= 56]
            peers = [value for other, value in rates.items() if other[2:] == key[2:] and other[:2] != key[:2]]
            historic = sum(history) / len(history) if history else None
            peer = sum(peers) / len(peers) if peers else None
            expected = {"cost_per_tonne_km": rate, "total_cost_inr": groups[key][0], "total_tonne_km": groups[key][1],
                        "history_average": historic, "peer_average": peer,
                        "history_change_percent": (rate / historic - 1) * 100 if historic else None,
                        "peer_change_percent": (rate / peer - 1) * 100 if peer else None}
            row = observed[key]
            if row["shipment_count"] != groups[key][2] or row["history_week_count"] != len(history) or row["peer_count"] != len(peers):
                raise ValueError(f"Observation/baseline counts differ for {key}.")
            for field, value in expected.items():
                actual = row[field]
                if (actual is None) != (value is None):
                    raise ValueError(f"Unavailable comparison differs for {key}: {field}.")
                if value is not None:
                    delta = abs(Decimal(str(actual)) - value)
                    largest = max(largest, delta)
                    if delta > Decimal("1e-9"):
                        raise ValueError(f"Numeric mismatch for {key}: {field}, delta={delta}.")
                comparisons += 1
        return {"route_weeks": len(rows), "field_checks": comparisons, "max_absolute_difference": str(largest), "tolerance": "1e-9"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shipments", type=Path, default=ROOT / "AI Intern Case Study/AI Intern Case Study/shipment_records.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    report, _, _ = read_bundle(args.output_dir)
    if hashlib.sha256(args.shipments.read_bytes()).hexdigest() != report["summary"]["input_sha256"]["shipments"]:
        raise ValueError("Input differs from the verified analysis.")
    result = check_numbers(args.shipments, report["rows"])
    print(f"Decimal verification: {result}")


if __name__ == "__main__":
    main()
