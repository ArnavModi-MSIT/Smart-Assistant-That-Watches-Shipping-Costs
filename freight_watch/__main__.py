import argparse
import hashlib
import json
from pathlib import Path
import sys
import platform
import tempfile
import os
import csv
import io
from time import perf_counter

from .engine import analyze
from .evaluation import evaluate
from .io import ROOT, DATA_DIR, OUTPUT_COLUMNS, write_json, write_output, file_hash
from .llm import QuoteWriter
from .models import Thresholds
from .bundle import source_files


def stable_hash(rows):
    values = [{key: row[key] for key in OUTPUT_COLUMNS if key != "reason"} for row in rows]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def numeric_hash(rows):
    fields = ("route", "week_of", "cost_per_tonne_km", "history_average", "peer_average",
              "history_change_percent", "peer_change_percent", "flagged", "matched_note_id")
    values = [{key: row[key] for key in fields} for row in rows]
    return hashlib.sha256(json.dumps(values, sort_keys=True, allow_nan=False).encode()).hexdigest()


def environment_info(writer):
    sources = source_files(ROOT)
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "machine": platform.machine(), "ollama": writer.model_info,
            "source_sha256": {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(sources) if p.is_file()}}


def publish(output_dir, reports, runs, evaluation, repeat, environment, command, strict):
    """Stage all files; commit the hash manifest last. Single runs invalidate repeat checks."""
    report = reports[0]
    evaluation_ok = evaluation["passed"] == evaluation["label_count"] and evaluation["all_justified_rows_have_eligible_citations"]
    report["summary"]["validation"] = {"command": command, "strict": strict, "evaluation_passed": evaluation_ok,
                                       "reproducibility_passed": repeat["passed"] if command == "verify" else None}
    with tempfile.TemporaryDirectory(prefix=".run-", dir=output_dir) as temporary:
        stage = Path(temporary).resolve()
        if not stage.is_relative_to(output_dir.resolve()):
            raise ValueError("Staging directory escaped the output directory.")
        write_output(stage / "output.csv", report["csv_rows"])
        for index, other in enumerate(reports[1:], 2):
            (stage / "verification").mkdir(exist_ok=True)
            write_output(stage / "verification" / f"run_{index}.csv", other["csv_rows"])
        files = {"results.json": report, "run_summary.json": report["summary"],
                 "token_cost_log.json": report["token_cost_log"], "evaluation.json": evaluation,
                 "reproducibility.json": repeat, "environment.json": environment}
        for name, value in files.items():
            write_json(stage / name, value)
        manifest = {"schema_version": 1, "command": command, "strict": strict, "evaluation_passed": evaluation_ok,
                    "reproducibility_passed": repeat["passed"] if command == "verify" else None,
                    "files": {p.relative_to(stage).as_posix(): file_hash(p) for p in sorted(stage.rglob("*")) if p.is_file()}}
        write_json(stage / "run_manifest.json", manifest)
        for source in sorted(stage.rglob("*")):
            if source.is_file() and source.name != "run_manifest.json":
                target = output_dir / source.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
        os.replace(stage / "run_manifest.json", output_dir / "run_manifest.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Monitor weekly freight costs and cite applicable evidence.")
    parser.add_argument("command", choices=["run", "verify", "serve"])
    parser.add_argument("--shipments", type=Path, default=DATA_DIR / "shipment_records.csv")
    parser.add_argument("--notes", type=Path, default=DATA_DIR / "context_notes.csv")
    parser.add_argument("--rules", type=Path, default=ROOT / "config" / "note_rules.json")
    parser.add_argument("--labels", type=Path, default=ROOT / "config" / "labeled_weeks.json")
    parser.add_argument("--require-evaluation-pass", action="store_true", help="Make exploratory run fail on reference or citation failures.")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--history-threshold", type=float, default=15)
    parser.add_argument("--peer-threshold", type=float, default=20)
    parser.add_argument("--minimum-rise", type=float, default=5)
    parser.add_argument("--llm-model", default=None, help="Optional local Ollama model; no hosted API calls.")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--llm-timeout", type=float, default=120)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve
            serve(args.output_dir, args.port, args.llm_model, args.ollama_url, args.llm_timeout)
            return 0
        thresholds = Thresholds(args.history_threshold, args.peer_threshold, args.minimum_rise)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        runs, reports = [], []
        initial_sources = environment_info(QuoteWriter())["source_sha256"]
        label_bytes = args.labels.read_bytes()
        label_hash = hashlib.sha256(label_bytes).hexdigest()
        for index in range(3 if args.command == "verify" else 1):
            writer = QuoteWriter(args.llm_model, args.ollama_url, args.llm_timeout, capture_environment=True)
            started = perf_counter()
            report = analyze(args.shipments, args.notes, thresholds, writer, args.rules)
            report["summary"]["analysis_wall_seconds"] = round(perf_counter() - started, 6)
            reports.append(report)
            rows = report["csv_rows"]
            # Hash the exact CSV bytes through a memory buffer; publish only after all analyses finish.
            stream = io.StringIO(newline="")
            csv_writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            csv_writer.writeheader()
            csv_writer.writerows(rows)
            runs.append({"run": index + 1, "csv": "output.csv" if index == 0 else f"verification/run_{index + 1}.csv",
                         "csv_sha256": hashlib.sha256(stream.getvalue().encode()).hexdigest(),
                         "stable_fields_sha256": stable_hash(rows), "full_precision_sha256": numeric_hash(report["rows"]),
                         "token_cost_log": writer.log(),
                         "input_sha256": report["summary"]["input_sha256"]})
            print(f"Run {index + 1}: {report['summary']['route_weeks']} route-weeks, "
                  f"{report['summary']['unexplained']} unexplained, {report['summary']['justified']} justified", flush=True)
            log = writer.log()
            if args.llm_model:
                print(f"AI: {log['accepted_quotes']} accepted quotes, {log['cache_hits']} cache hits, "
                      f"{log['source_quote_fallbacks']} source fallbacks ({log['calls_failed']} failed calls).", flush=True)
        report = reports[0]
        current_hashes = {"shipments": file_hash(args.shipments), "notes": file_hash(args.notes), "note_rules": file_hash(args.rules)}
        if any(r["input_sha256"] != current_hashes for r in runs):
            raise ValueError("Inputs changed during analysis; rerun before publishing.")
        if file_hash(args.labels) != label_hash:
            raise ValueError("Reference labels changed during analysis; rerun before publishing.")
        environment = environment_info(writer)
        if environment["source_sha256"] != initial_sources:
            raise ValueError("Source code changed during analysis; rerun before publishing.")
        environment["reference_labels_sha256"] = label_hash
        evaluation = evaluate(report, args.labels, args.rules, labels_bytes=label_bytes)
        evaluation_ok = evaluation["passed"] == evaluation["label_count"] and evaluation["all_justified_rows_have_eligible_citations"]
        repeat = {"passed": False, "status": "not_run", "same_full_csv": None,
                  "reason": "A single run does not verify reproducibility; previous repeat evidence is invalidated.", "runs": runs}
        if args.command == "verify":
            stable = (len({r["stable_fields_sha256"] for r in runs}) == 1
                      and len({r["full_precision_sha256"] for r in runs}) == 1
                      and len({json.dumps(r["input_sha256"], sort_keys=True) for r in runs}) == 1)
            repeat = {"passed": stable and evaluation_ok, "status": "passed" if stable and evaluation_ok else "failed",
                      "stability_passed": stable, "evaluation_passed": evaluation_ok,
                      "same_full_csv": len({r["csv_sha256"] for r in runs}) == 1,
                      "compared_columns": [c for c in OUTPUT_COLUMNS if c != "reason"],
                      "reason": "Explanation wording may vary; flags, cited note, verdict and numbers must not.", "runs": runs}
        strict = args.command == "verify" or args.require_evaluation_pass
        # Evaluation also reads reviewed rules. Reject edits made during that stage.
        if (current_hashes != {"shipments": file_hash(args.shipments), "notes": file_hash(args.notes), "note_rules": file_hash(args.rules)}
                or file_hash(args.labels) != label_hash
                or environment_info(writer)["source_sha256"] != initial_sources):
            raise ValueError("Inputs, labels or source code changed during evaluation; rerun before publishing.")
        publish(args.output_dir, reports, runs, evaluation, repeat, environment, args.command, strict)
        if strict and not evaluation_ok:
            raise ValueError(f"Reference/citation evaluation failed ({evaluation['passed']}/{evaluation['label_count']}); see evaluation.json.")
        if args.command == "verify":
            if not repeat["stability_passed"]:
                raise ValueError("Reproducibility failed; inspect reproducibility.json.")
            print("Strict verification: PASS (reference checks, citations and three-run stability)", flush=True)
        print(f"Labeled checks: {evaluation['passed']}/{evaluation['label_count']}. Output: {args.output_dir.resolve()}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
