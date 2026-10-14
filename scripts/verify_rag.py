"""Run labeled retrieval/generation checks; retain exact real prompts and responses."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from freight_watch.bundle import read_bundle, source_files
from freight_watch.io import write_json
from freight_watch.rag import RagAssistant

CASES = [
    ("festival", "Why Ahmedabad-Mumbai on 2025-01-20?", "F:Ahmedabad-Mumbai:2025-01-20", "No (justified)"),
    ("expired_flood", "Why Chennai-Bangalore on 2025-03-10?", "F:Chennai-Bangalore:2025-03-10", "Yes"),
    ("partial_flood", "Why Chennai-Bangalore on 2025-03-03?", "F:Chennai-Bangalore:2025-03-03", "No (justified)"),
    ("nonimpact", "What does note N010 say?", "N010", None),
    ("future_festival", "Why Ahmedabad-Mumbai on 2025-01-13?", "F:Ahmedabad-Mumbai:2025-01-13", "No"),
    ("reverse_route", "Why Mumbai-Ahmedabad on 2025-01-20?", None, None),
    ("empty_status", "Show justified Ahmedabad-Mumbai on 2025-01-13", None, None),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--llm-model")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--llm-timeout", type=float, default=120)
    parser.add_argument("--save", type=Path, default=ROOT / "evidence/rag_verification.json")
    args = parser.parse_args()
    report, snapshot, _ = read_bundle(args.output_dir, require_verified=True)
    verified_sources = json.loads(snapshot["environment.json"])["source_sha256"]
    def current_sources():
        return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files(ROOT)}
    if current_sources() != verified_sources:
        raise ValueError("Source code differs from the verified run; verify again before recording RAG evidence.")
    assistant = RagAssistant(report, args.llm_model, args.ollama_url, args.llm_timeout)
    checks = []
    for name, question, expected, flag in CASES:
        response = assistant.answer(question); rag = response["rag"]
        retrieved = {doc["source_id"] for doc in rag["retrieved"]}
        used = {item["source_id"] for item in rag.get("answer_plan", {}).get("items", [])}
        matched = (expected in retrieved and expected in used) if expected else not retrieved and not response["findings"]
        verdict_ok = flag is None or any(f["flagged"] == flag for f in response["findings"])
        generation_ok = not (args.llm_model and expected) or rag["mode"] == "local_llm"
        passed = matched and verdict_ok and generation_ok
        checks.append({"case": name, "question": question, "expected_source": expected, "expected_verdict": flag,
                       "retrieval_and_selection_passed": matched, "verdict_passed": verdict_ok,
                       "live_generation_passed": generation_ok, "passed": passed, "result": response})
        print(f"{name}: {'PASS' if passed else 'FAIL'} ({rag['mode']})", flush=True)
    first = assistant.answer(CASES[0][1])
    cache_ok = not args.llm_model or first["rag"]["mode"] == "local_llm_cached" and first["rag"]["usage"]["input_tokens"] == 0
    calls = [c["result"]["rag"]["usage"] for c in checks if c["result"]["rag"].get("usage")]
    record = {"passed": all(c["passed"] for c in checks) and cache_ok, "case_count": len(checks),
              "passed_cases": sum(c["passed"] for c in checks), "cache_check_passed": cache_ok,
              "model": args.llm_model, "model_info": assistant.writer.model_info,
              "llm_calls": len(calls), "input_tokens": sum(c["input_tokens"] for c in calls) if all(c["input_tokens"] is not None for c in calls) else None,
              "output_tokens": sum(c["output_tokens"] for c in calls) if all(c["output_tokens"] is not None for c in calls) else None,
              "hosted_api_cost_usd": 0., "cost_basis": "Local Ollama; hardware/electricity cost unmeasured.",
              "run_manifest_sha256": hashlib.sha256(snapshot["run_manifest.json"]).hexdigest(),
              "source_sha256": verified_sources,
              "evaluation_scope": "Seven authored cases; not a general language or anomaly accuracy benchmark.", "checks": checks}
    if current_sources() != verified_sources:
        raise ValueError("Source code changed during RAG verification; rerun before saving evidence.")
    args.save.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.save, record)
    print(f"RAG: {record['passed_cases']}/{len(checks)}; {len(calls)} actual model calls. Saved {args.save}")
    return 0 if record["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
