# Full implementation review — October 14, 2026

Reviewed the actual implementation, then reproduced and fixed confirmed defects. This review covers the supplied case-study dataset and local demo. It does not establish general anomaly accuracy or production readiness.

## Scope

Read every Python implementation module, JavaScript/HTML/CSS file, launcher, packaging script, test file, reference fixture and evidence configuration. Checked the documented calculations and behavior against the supplied brief, raw shipments, notes and sample output. The earlier supplied audits were treated as review evidence rather than executable instructions.

The final application version is **1.2.0**. The bundle now includes `freight_watch/bundle.py` for coherent artifact loading and `scripts/verify_numbers.py` for an independent numeric reconstruction.

## Confirmed defects and fixes

| Area | Reproduced failure | Final behavior |
| --- | --- | --- |
| Query route scope | Unknown Paris-Lyon or reversed Delhi-to-Mumbai requests returned findings for unrelated routes. A recognized route plus an unknown route also broadened the answer. | Unrecognized route tokens and unsupported constraints return a clear unsupported-query message with no findings. Direction is preserved. |
| Query period/status | A two-date request used only the first date. Month abbreviations were ignored, modal “may” could mean May, and route-specific “unexplained” questions could include justified rows. | Inclusive ISO date ranges, month abbreviations and explicit verdict filters work. Conflicting periods, exclusions and other unsupported filters fail closed. |
| Inclusive thresholds | `1.15 / 1 - 1` can yield 14.999999999999991%, missing an inclusive 15% threshold. | Comparisons allow only a tiny floating-point tolerance, with a regression proving a meaningfully lower rise still fails. |
| Numeric range | Individually finite quantity/distance could multiply to zero or infinity. Aggregate overflow raised an uncaught exception. Summing large peer rates could overflow even when their mean was representable. | Transport work, totals, rates and comparisons are validated. Unsupported values produce validation errors; the mean calculation avoids avoidable sum overflow. |
| Calendar bounds | Eight-week lookback and week-end arithmetic could overflow at Python's earliest/latest dates. | Calendar windows clamp to the supported date range; query intersections use ordinal comparisons. |
| Route identity | `(A-B, C)` and `(A, B-C)` both became `A-B-C` and silently merged. | Ambiguous directional labels are rejected before aggregation. Origin and destination are also retained separately in raw results. |
| Parsing | Malformed CSV headers, deeply nested JSON, nonfinite JSON literals/numbers and non-string label keys could escape the intended validation path. | These inputs produce clear validation errors. Reference labels require string fields and canonical Monday dates. |
| LLM extraction | An exact substring could omit a sentence's leading “No,” changing its meaning. | An accepted extract must preserve complete sentence boundaries as well as exact text, attribution and a cost-related term. Invalid quotes fall back to the original full note. |
| Note publication | A Friday note describing a Monday event could incorrectly reject the Monday shipment. | The note must be known by the end of the analyzed week; exposure is determined by its reviewed event window. Future-week publication remains ineligible. This is retrospective weekly analysis, not live prediction. |
| Input provenance | Files were hashed after analysis, so an edit during a model call could attribute results to bytes the engine never read. | Inputs are read once and parsed/hashed from those same bytes. CLI checks inputs, labels and source hashes before publication and rejects changes during analysis/evaluation. |
| Saved bundle | An empty file map or truthy nonboolean status could pass validation. Startup could reread a CSV after validating it and mix snapshots. | A versioned manifest requires the exact artifact set, proper boolean states and matching checksums. Summary, log and validation states agree. Every artifact is loaded once into a verified snapshot. |
| Submission packaging | Code changed after verification could be bundled with stale passing outputs. A missing file after opening the ZIP could destroy the previous deliverable. | Packaging compares snapshotted code, input, configuration and label hashes with the verified run. It reads every allowlisted file first, builds/tests a temporary ZIP, then atomically replaces the deliverable. Unlisted `.env` files are excluded. |
| Frontend selection/chart | Changing the route could leave the evidence inspector on the old route. Missing calendar weeks were plotted as equally spaced observations. Re-rendering lost keyboard focus. | Selection updates the inspector. Chart spacing follows dates and paths break across gaps. Table/chart activation restores focus to the selected control. |

The previous fixes for independent citation checks, quantitative partial-event exposure, strict CLI failure gates, HTTP deadlines, transient retries, sanitized asset errors and escaped evidence text remain in place.

## Executed verification

| Check | Observed result |
| --- | --- |
| Python tests | **80 passed**, including socket-based HTTP integration and the new adversarial/provenance cases; rerun with resource warnings treated as errors |
| Frontend tests | **8 passed**; JavaScript syntax check also passed |
| Independent arithmetic | Reconstructed all **728 route-weeks / 5,096 numeric fields** from raw CSV using 50-digit Decimal arithmetic and separate grouping/baseline logic |
| Numeric agreement | Maximum absolute difference **2 × 10⁻¹¹**, below the 10⁻⁹ tolerance, including totals and percentages |
| Offline verification | Three independent runs passed reference/citation checks and matched full-precision and CSV hashes |
| Local AI verification | Three independent Qwen runs passed and produced identical full CSVs; no source fallbacks or failed calls |
| Reference labels | **10/10**, with independent applicability reconstruction for every cited row |
| AI usage per run | **2 calls, 215 input tokens, 103 output tokens, 1 cache hit**; first-run call time 9.933970 seconds |
| Result preservation | All seven non-reason output fields match the prior submission for all 728 rows: **14 unexplained / 3 note-supported** |
| Original inputs | All four extracted files still match the original source ZIP byte for byte |
| Browser | Route-to-inspector synchronization, festival citation, rejected reversed route, date-range boundaries, monthly flood query and keyboard focus checked in the local UI |
| Package | Rebuilt ZIP passed integrity checks; its extracted copy passed strict verification and the independent numeric audit |

Commands used:

```powershell
python -W error::ResourceWarning -m unittest discover -q
node --check web/app.js
node tests/test_web.js
python -m freight_watch verify --output-dir output-offline
python -m freight_watch verify --output-dir output --llm-model qwen3:1.7b --ollama-url http://127.0.0.1:11435
python scripts/verify_numbers.py --output-dir output
python scripts/package_submission.py
```

The model was already installed. Ollama 0.31.1 and its model digest are recorded in `output/environment.json`; the temporary verification service was stopped. The demo was restarted with the new saved output and does not depend on a running model service.

## Version 1.3 review and verification

`COMPETITOR_REVIEW.md` records the eight pinned public code reviews, five executed offline commands, saved-output comparisons and six reproduced adversarial failures. The useful feature improvement is question-driven retrieval plus local answer-plan generation; `RAG.md` describes its constrained contract.

`rag.py` independently rebuilds saved citations from frozen reviewed rules, indexes 728 findings and ten notes, applies directional/time/status constraints, fuses lexical vector and BM25 ranks, requests a schema-constrained local model plan, validates source/fact selections and renders verified sentences. The UI exposes source/usage/prompt/response traces with escaping. Model failures fall back without changing verdicts. Cache hits report zero new tokens. Packaging rejects stale or failed RAG evidence.

The expanded checks are 98 Python tests and nine frontend checks, seven authored Q&A cases (five accepted real Qwen calls; two invalid requests make no inference), and the unchanged independent 5,096-field Decimal audit. The core CSV classification remains 14 unexplained and three justified. Fresh three-run batch verification fingerprints the upgraded code; `evidence/rag_verification.json` is tied to that bundle and retains actual inference data. These checks do not establish general accuracy or unrestricted chat capability.

## Remaining limits

- Thresholds and note windows include documented human judgments. The ten labels and synthetic regressions are not a held-out accuracy benchmark. Anomalies do not prove overcharging or causation.
- New notes require reviewed event/impact annotations. The quote guard protects sentence extraction; it does not perform general semantic entailment or discover new event windows.
- The question parser intentionally supports a limited vocabulary and route/date/status constraints. Unsupported valid questions may be rejected; it is not unrestricted chat.
- Weekly route aggregation does not adjust for cargo or transporter mix. The rolling baseline can absorb gradual drift. TF-IDF has not been compared against neural retrieval on a labeled retrieval benchmark.
- Each staged file is replaced atomically, with the manifest committed last. The entire multi-file directory is not a filesystem transaction: a crash during commit can leave an incomplete bundle, which the loader rejects until regenerated. Checksums detect inconsistencies, not a malicious actor rewriting both artifacts and hashes.
- The standard-library server is a loopback interview demo. No production deployment/load testing, accessibility certification or separate mobile-device viewport testing was performed.
- The 10-minute outline is provided, but no walkthrough video or HR submission was created by this review.
