"""Snapshot an explicit allowlist and atomically replace the verified submission ZIP."""

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from freight_watch.bundle import read_bundle, source_files
from freight_watch.io import decode_json

FILES = ["README.md", "WALKTHROUGH.md", "VALIDATION.md", "RAG.md",
         "requirements.txt", ".gitignore", "config/note_rules.json", "tests/fixtures/labeled_weeks.json"]
INPUT_DIR = Path("AI Intern Case Study") / "AI Intern Case Study"
INPUTS = ["shipment_records.csv", "context_notes.csv", "sample_output_format_v2.csv", "FreightTiger_Intern_CaseStudy.pdf"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build_package(root=ROOT, target=None):
    root = Path(root).resolve()
    target = root / "FreightWatch_Submission.zip" if target is None else Path(target).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Submission target must stay inside the workspace.")
    report, outputs, _manifest = read_bundle(root / "output", require_verified=True)
    selected = source_files(root) + [root / name for name in FILES] + [root / INPUT_DIR / name for name in INPUTS]
    snapshot = {}
    for path in sorted(set(selected)):
        if not path.resolve().is_relative_to(root):
            raise ValueError("A package file escaped the workspace.")
        snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    environment = decode_json(outputs["environment.json"], "Run environment")
    current_sources = {p.relative_to(root).as_posix(): digest(snapshot[p.relative_to(root).as_posix()]) for p in source_files(root)}
    if not isinstance(environment, dict) or environment.get("source_sha256") != current_sources:
        raise ValueError("Source code differs from the verified run; run strict verify again before packaging.")
    current_inputs = {"shipments": digest(snapshot[(INPUT_DIR / INPUTS[0]).as_posix()]),
                      "notes": digest(snapshot[(INPUT_DIR / INPUTS[1]).as_posix()]),
                      "note_rules": digest(snapshot["config/note_rules.json"])}
    if report["summary"].get("input_sha256") != current_inputs:
        raise ValueError("Packaged inputs differ from the verified run.")
    if environment.get("reference_labels_sha256") != digest(snapshot["tests/fixtures/labeled_weeks.json"]):
        raise ValueError("Reference labels differ from the verified run.")
    snapshot.update({"output/" + name: raw for name, raw in outputs.items()})
    path = root / "evidence/rag_verification.json"
    if path.is_file():
        raw = path.read_bytes()
        verification = decode_json(raw, "RAG verification")
        if (not isinstance(verification, dict) or verification.get("passed") is not True
                or verification.get("source_sha256") != current_sources
                or verification.get("run_manifest_sha256") != digest(outputs["run_manifest.json"])):
            raise ValueError("RAG evidence differs from the verified run or failed; rerun verify_rag.py.")
        snapshot["evidence/rag_verification.json"] = raw
    preview = root / "output" / "demo_preview.jpg"
    if preview.is_file():
        snapshot["output/demo_preview.jpg"] = preview.read_bytes()
    # Read/validate every source before touching the existing deliverable.
    handle, name = tempfile.mkstemp(prefix=".submission-", suffix=".zip", dir=root)
    os.close(handle)
    staged = Path(name)
    try:
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in sorted(snapshot.items()):
                archive.writestr(name, raw)
        with zipfile.ZipFile(staged) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"Corrupt package entry: {bad}")
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
    return target, len(snapshot)


def main():
    target, count = build_package()
    print(f"{target.name}: {count} files, {target.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
