"""Reviewed source and quantitative event exposure gate retrieved justifications."""

from datetime import date
import math

from .io import decode_json, note_hash

_UNSET = object()


class EvidenceMatcher:
    def __init__(self, notes, rules_path, index, weekly_rows=(), config=_UNSET):
        if config is _UNSET:
            with open(rules_path, encoding="utf-8") as stream:
                config = decode_json(stream.read(), "Note rules")
        if not isinstance(config, dict) or not isinstance(config.get("notes"), dict):
            raise ValueError("Note rules must contain a notes object.")
        self.rules = config["notes"]
        self.index = index
        self.notes = {n.note_id: n for n in notes}
        self.weeks = {(r["route"], r["week_of"]): r for r in weekly_rows}
        self.policy = config.get("policy", {})
        if not isinstance(self.policy, dict):
            raise ValueError("Evidence policy must be an object.")
        self.uplift_tolerance = self.policy.get("uplift_tolerance_percent", 2.0)
        self.uncovered_limit = self.policy.get("uncovered_rise_percent", 5.0)
        for value in (self.uplift_tolerance, self.uncovered_limit):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Evidence tolerances must be finite, nonnegative percentages.")
        if self.uncovered_limit == 0:
            raise ValueError("Uncovered-rise threshold must be positive.")
        for note_id, rule in self.rules.items():
            if not isinstance(rule, dict) or not isinstance(rule.get("supports_cost_increase"), bool):
                raise ValueError(f"Invalid impact annotation for {note_id}.")
            if not isinstance(rule.get("source_sha256"), str):
                raise ValueError(f"Missing source hash for {note_id}.")
            if rule["supports_cost_increase"]:
                try:
                    start = date.fromisoformat(rule["effective_start"])
                    end = date.fromisoformat(rule["effective_end"]) if rule.get("effective_end") else date.max
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError(f"Invalid event dates for {note_id}.") from exc
                if end < start:
                    raise ValueError(f"Event end precedes start for {note_id}.")
                uplift = rule.get("maximum_uplift_percent")
                if uplift is not None and (isinstance(uplift, bool) or not isinstance(uplift, (int, float)) or not math.isfinite(uplift) or uplift < 0):
                    raise ValueError(f"Invalid uplift for {note_id}.")
            elif not isinstance(rule.get("exclusion_reason"), str):
                raise ValueError(f"Missing exclusion reason for {note_id}.")
        for note in notes:
            rule = self.rules.get(note.note_id)
            if rule and rule["source_sha256"] != note_hash(note):
                raise ValueError(f"{note.note_id} changed: review its event annotation before running.")
        orphaned = sorted(set(self.rules) - set(self.notes))
        if orphaned:
            raise ValueError("Annotations reference absent notes: " + ", ".join(orphaned))

    def assessment(self, note, row):
        rule = self.rules.get(note.note_id)
        week = date.fromisoformat(row["week_of"])
        end_week = date.fromordinal(min(date.max.toordinal(), week.toordinal() + 6))
        result = {"eligible": False, "check": "", "exposure": None}

        def reject(message):
            result["check"] = message
            return result

        if note.applies_to not in (row["route"], "All Routes"):
            return reject("Different route.")
        if note.day > end_week:
            return reject("Note was published after this week.")
        if not rule:
            return reject("Unreviewed note: no verified cost-impact window.")
        if not rule["supports_cost_increase"]:
            return reject(rule["exclusion_reason"])
        start = date.fromisoformat(rule["effective_start"])
        end = date.fromisoformat(rule["effective_end"]) if rule.get("effective_end") else date.max
        days = row.get("daily_totals", [])
        if not days:
            return reject("No quantitative shipment-date exposure is available; manual review required.")
        affected = [d for d in days if start <= date.fromisoformat(d["date"]) <= end]
        if not affected:
            return reject("Event window does not cover any shipment date in this week.")
        affected_work = math.fsum(d["tonne_km"] for d in affected)
        total_work = row["total_tonne_km"]
        uncovered = [d for d in days if d not in affected]
        baseline = row["history_average"]
        uncovered_work = math.fsum(d["tonne_km"] for d in uncovered)
        uncovered_cost = math.fsum(d["cost_inr"] for d in uncovered)
        residual = max(0, (uncovered_cost / total_work) / baseline - uncovered_work / total_work) * 100 if baseline else None
        result["exposure"] = {"affected_tonne_km_fraction": min(1.0, affected_work / total_work),
                              "affected_shipments": sum(d["shipments"] for d in affected),
                              "uncovered_rise_percent": residual}
        if uncovered and (residual is None or residual >= self.uncovered_limit):
            return reject(f"Partial event exposure leaves an uncovered weekly rise of {residual:.1f}% requiring review." if residual is not None else "Partial exposure without a baseline requires review.")
        history = row["history_weeks"]
        previous = [self.weeks.get((row["route"], w)) for w in history]
        if previous and all(previous) and all(r.get("daily_totals") for r in previous):
            before = [math.fsum(d["tonne_km"] for d in r["daily_totals"] if date.fromisoformat(d["date"]) < start) / r["total_tonne_km"] for r in previous]
            fraction_before = math.fsum(before) / len(before)
        else:
            if history and start.weekday() != 0:
                return reject("Historical event exposure is unavailable for this mid-week change.")
            fraction_before = sum(date.fromisoformat(w) < start for w in history) / len(history) if history else 1
        if history and fraction_before == 0:
            return reject("Event is already included throughout the historical baseline.")
        if rule.get("maximum_uplift_percent") is not None and row["history_change_percent"] is not None:
            bound = rule["maximum_uplift_percent"] * fraction_before + self.uplift_tolerance
            if row["history_change_percent"] > bound:
                return reject(f"Observed rise exceeds the note's stated uplift (allowance {bound:.1f}%).")
        result.update(eligible=True, check="Route, publication date, shipment exposure and cost impact match.")
        return result

    def eligibility(self, note, row):
        result = self.assessment(note, row)
        return result["eligible"], result["check"]

    def match(self, row):
        ranked = self.index.search(f"{row['route']} {row['route_type']} {row['week_of']} freight cost increase")
        inspected = []
        for note, score in ranked:
            check = self.assessment(note, row)
            item = {"note_id": note.note_id, "score": round(score, 6),
                    "eligible": check["eligible"], "check": check["check"]}
            if check["exposure"] is not None:
                item["exposure"] = check["exposure"]
            inspected.append(item)
        valid = [item for item in inspected if item["eligible"]]
        # Examine all ten notes. A top-k cut must not hide valid global context.
        if not valid:
            return None, inspected
        chosen = valid[0]  # Search already orders by descending score, then note ID.
        source = self.notes[chosen["note_id"]]
        return dict(chosen, date=source.day.isoformat(), applies_to=source.applies_to, text=source.text), inspected
