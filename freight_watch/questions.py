"""Conservative natural-language query parsing over computed results."""

from collections import Counter
from calendar import monthrange
from datetime import date, timedelta
import re

MONTHS = {name.lower(): index for index, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})
MONTHS["sept"] = 9
QUERY_WORDS = set("which what why how did do does is are was were has have had the a an these those this that "
                  "route routes shipping freight cost costs rate rates need needs review flagged unexplained "
                  "expensive increase increases increased rise rises rising higher high unusual jump jumped "
                  "spike spiked changed change happened explain show list findings observations get pricier for on in at "
                  "during of over and to towards from between through week weeks month year please me all "
                  "than their its past average history versus vs may can you tell about supported justified normal "
                  "there surcharge surcharges truck availability issue issues festival festivals flood flooding "
                  "weather diesel fuel prices highway maintenance cause caused impact tracking mandate "
                  "note notes say says rejected rejection evidence explain summary summarize compare difference "
                  "between expensive cheaper price movement".split())


def unsupported():
    return {"answer": "I could not apply every requested constraint. Use a listed directional route, a date or date range in YYYY-MM-DD, or one month and year. Exclusions and other filters are unsupported.", "findings": []}


def question_scope(question, report):
    text = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    rows = report["rows"]
    note_ids = re.findall(r"\bN\d{3}\b", question.upper())
    if any(note_id not in {n["note_id"] for n in report["notes"]} for note_id in note_ids):
        return unsupported()
    routes = sorted({r["route"] for r in rows})
    selected = []
    residual = re.sub(r"\bn\d{3}\b", " ", text)
    for route in routes:
        name = re.sub(r"[^a-z0-9]+", " ", route.lower())
        words = name.split()
        pattern = r"\b" + r"(?:\s+(?:to|and|towards|from)\s+|\s+)".join(map(re.escape, words)) + r"\b"
        if re.search(pattern, text):
            selected.append(route)
            residual = re.sub(pattern, " ", residual)
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", question)
    if re.search(r"\b(except|excluding|exclude|not|without|other than)\b", text):
        return unsupported()
    if re.search(r"\b(today|yesterday|now|current|currently)\b", text):
        return {"answer": "The supplied data ends on " + report["summary"]["date_end"] + ". Ask for a date within that dataset.", "findings": []}
    for literal in dates:
        residual = residual.replace(literal.replace("-", " "), " ")
    years = re.findall(r"\b\d{4}\b", residual)
    months = {number for name, number in MONTHS.items() if re.search(r"\b" + name + r"\b", text)
              and (name != "may" or years or re.search(r"\b(?:in|during|for) may\b", text))}
    if len(months) > 1 or len(set(years)) > 1 or dates and months:
        return unsupported()
    month = next(iter(months), None)
    for name, number in MONTHS.items():
        if number in months:
            residual = re.sub(r"\b" + name + r"\b", " ", residual)
    residual = re.sub(r"\b\d{4}\b", " ", residual)
    if any(word not in QUERY_WORDS for word in residual.split()):
        return unsupported()
    scope = rows
    if selected:
        scope = [r for r in scope if r["route"] in selected]
    if dates:
        if len(dates) > 2 or len(dates) == 2 and not re.search(r"\b(between|from|to|through)\b", text):
            return unsupported()
        try:
            first = date.fromisoformat(dates[0])
            last = date.fromisoformat(dates[-1])
        except ValueError:
            return {"answer": "That date is invalid. Use YYYY-MM-DD.", "findings": []}
        if first > last or years:
            return unsupported()
        first_week = (first - timedelta(days=first.weekday())).isoformat()
        last_week = (last - timedelta(days=last.weekday())).isoformat()
        scope = [r for r in scope if first_week <= r["week_of"] <= last_week]
    elif month is not None:
        if not years:
            return {"answer": "Please include the year. The dataset covers " + report["summary"]["date_start"] + " through " + report["summary"]["date_end"] + ".", "findings": []}
        year = int(years[0])
        if not 1 <= year <= 9999:
            return unsupported()
        first, last = date(year, month, 1), date(year, month, monthrange(year, month)[1])
        scope = [r for r in scope if date.fromisoformat(r["week_of"]) <= last and date.fromisoformat(r["week_of"]).toordinal() + 6 >= first.toordinal()]
    elif years:
        year = int(years[0])
        if not 1 <= year <= 9999:
            return unsupported()
        scope = [r for r in scope if date.fromisoformat(r["week_of"]) <= date(year, 12, 31) and date.fromisoformat(r["week_of"]).toordinal() + 6 >= date(year, 1, 1).toordinal()]
    if not scope:
        return {"answer": f"No matching route-week exists. Specify a listed route and a date between {report['summary']['date_start']} and {report['summary']['date_end']}.", "findings": []}
    requested = set()
    if re.search(r"\b(unexplained|flagged|needs? review)\b", text):
        requested.add("Yes")
    if re.search(r"\b(justified|supported)\b", text):
        requested.add("No (justified)")
    if re.search(r"\bnormal\b", text):
        requested.add("No")
    if len(requested) > 1:
        return unsupported()
    requested_flag = next(iter(requested), None)
    return {"rows": scope, "routes": selected, "status": requested_flag, "note_ids": note_ids}


def answer_question(question, report):
    parsed = question_scope(question, report)
    if "rows" not in parsed:
        return parsed
    scope, selected, requested_flag = parsed["rows"], parsed["routes"], parsed["status"]
    text = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    if selected:
        findings = [r for r in scope if r["flagged"] == requested_flag] if requested_flag else [r for r in scope if r["candidate"]]
        if not findings:
            if requested_flag:
                return {"answer": "No observations match that status in the requested scope.", "findings": []}
            findings = sorted(scope, key=lambda r: r["week_of"], reverse=True)[:3]
            heading = "No unusual rise was detected for that route and period. Latest matching observations:"
        else:
            heading = f"Found {len(findings)} matching route-week(s) in the requested scope. Latest findings:"
    elif re.search(r"\b(route|routes|review|flagged|unexplained|expensive|cost|costs)\b", text):
        flag = requested_flag or "Yes"
        findings = [r for r in scope if r["flagged"] == flag]
        counts = Counter(r["route"] for r in findings)
        status = {"Yes": "Unexplained increases", "No (justified)": "Note-supported increases", "No": "Normal observations"}[flag]
        heading = (status + " by route: " + "; ".join(f"{route}: {count} week(s)" for route, count in sorted(counts.items())) + ".") if counts else "No observations match that status in the requested scope."
    else:
        return {"answer": "I can answer questions about these shipping findings. Include a route and date, or ask which routes need review.", "findings": []}
    findings = sorted(findings, key=lambda r: (r["week_of"], r["route"]), reverse=True)[:5]
    lines = [heading]
    for row in findings:
        change = f"{row['history_change_percent']:+.1f}%" if row["history_change_percent"] is not None else "unavailable"
        lines.append(f"{row['route']}, week {row['week_of']}: INR {row['cost_per_tonne_km']:.2f}/tonne-km; history comparison {change}; {row['reason']}")
    return {"answer": "\n\n".join(lines), "findings": [{"route": r["route"], "week_of": r["week_of"], "flagged": r["flagged"], "matched_note_id": r["matched_note_id"]} for r in findings]}
