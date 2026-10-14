"""Read every committed artifact once and validate a coherent saved snapshot."""

import hashlib
from pathlib import Path
import re

from .io import decode_json

CORE_FILES = {"output.csv", "results.json", "run_summary.json", "token_cost_log.json", "evaluation.json",
              "reproducibility.json", "environment.json", "threshold_sensitivity.json"}


def source_files(root):
    result = []
    for folder in ("freight_watch", "web", "scripts", "tests"):
        result.extend(p for p in (root / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                      and p.suffix in {".py", ".js", ".css", ".html"})
    result.extend(root / name for name in ("start_demo.ps1", "start_demo.cmd"))
    return sorted(set(result))


def read_bundle(output_dir, require_verified=False):
    output_dir = Path(output_dir).resolve()
    manifest_bytes = (output_dir / "run_manifest.json").read_bytes()
    manifest = decode_json(manifest_bytes, "Output manifest")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Invalid output manifest version; regenerate the analysis.")
    if manifest.get("command") not in ("run", "verify") or not isinstance(manifest.get("strict"), bool):
        raise ValueError("Invalid output manifest command or validation mode.")
    if not isinstance(manifest.get("evaluation_passed"), bool):
        raise ValueError("Invalid output manifest evaluation status.")
    if manifest["command"] == "verify":
        if manifest["strict"] is not True or not isinstance(manifest.get("reproducibility_passed"), bool):
            raise ValueError("Verification manifest must contain strict boolean validation states.")
    elif manifest.get("reproducibility_passed") is not None:
        raise ValueError("A single-run manifest cannot certify reproducibility.")
    expected = CORE_FILES | ({"verification/run_2.csv", "verification/run_3.csv"} if manifest["command"] == "verify" else set())
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != expected:
        raise ValueError("Output manifest is incomplete or contains unexpected files.")
    snapshot = {}
    for name, digest in files.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid output checksum.")
        target = (output_dir / name).resolve()
        if not target.is_relative_to(output_dir):
            raise ValueError("Output file escaped the bundle directory.")
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Output bundle changed or is incomplete; regenerate the analysis.")
        snapshot[name] = raw
    verified = manifest["command"] == "verify" and manifest["evaluation_passed"] and manifest["reproducibility_passed"]
    if manifest["strict"] and (not manifest["evaluation_passed"] or manifest["command"] == "verify" and not verified):
        raise ValueError("Strict verification failed; fix the evaluation before using this bundle.")
    if require_verified and not verified:
        raise ValueError("Submission requires a passing strict verify, not an exploratory single run.")
    report = decode_json(snapshot["results.json"], "Saved analysis")
    if (not isinstance(report, dict) or not isinstance(report.get("summary"), dict)
            or not isinstance(report.get("rows"), list) or not report["rows"]
            or not isinstance(report.get("notes"), list) or not isinstance(report.get("token_cost_log"), dict)):
        raise ValueError("Invalid or empty saved analysis; regenerate the output.")
    validation = {key: manifest[key] for key in ("command", "strict", "evaluation_passed", "reproducibility_passed")}
    if report["summary"].get("validation") != validation:
        raise ValueError("Saved analysis and manifest validation states differ.")
    if decode_json(snapshot["run_summary.json"], "Run summary") != report["summary"]:
        raise ValueError("Saved analysis and run summary differ.")
    if decode_json(snapshot["token_cost_log.json"], "Token log") != report["token_cost_log"]:
        raise ValueError("Saved analysis and token log differ.")
    snapshot["run_manifest.json"] = manifest_bytes
    return report, snapshot, manifest
