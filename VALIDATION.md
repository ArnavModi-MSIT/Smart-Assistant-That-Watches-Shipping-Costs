# Validation record

Verified locally on October 14, 2026 (India time), using the supplied inputs and default thresholds.

## Results

| Check | Observed result |
| --- | --- |
| Input coverage | 2,940 shipments, seven routes, 104 weeks |
| Output coverage | 728 route-week rows, exact eight-column header |
| Anomalous route-weeks | 17 candidates: 14 unexplained, three justified |
| Labeled reference cases | 10/10 passed; this small set is not a general accuracy estimate |
| Python test suite | 98 tests passed, including grounded RAG regressions; resource warnings treated as errors |
| JavaScript syntax | `node --check web/app.js` passed |
| Frontend resilience/rendering | Nine Node checks passed, including escaped RAG trace rendering |
| Independent arithmetic | 728 route-weeks / 5,096 numeric fields checked with 50-digit Decimal; maximum absolute difference 2 × 10⁻¹¹ |
| Offline repetition | Three unchanged runs; identical stable fields and full CSVs |
| Local AI repetition | Three unchanged runs; identical stable fields and full CSVs |
| AI token accounting | Two successful calls, 215 input tokens and 103 output tokens; two accepted quotes and one cache hit |
| Grounded Q&A | Seven authored cases passed; five accepted actual Qwen plans, two invalid scopes rejected without inference; cache check passed |
| Failure gate | Repeated incorrect output under extreme thresholds returns exit code 1 |
| Full precision | Three runs match full-precision numeric hashes as well as CSV fields |
| Model provenance | Ollama 0.31.1 and model digest recorded in environment and token logs |
| Hosted API spend | USD 0; local compute/electricity unmeasured |
| Supplied files | Extracted source files match the original ZIP byte for byte |
| Submission package | ZIP integrity passed; an extracted copy executed successfully and reproduced 728 route-weeks with 10/10 reference checks |

Detailed machine-readable evidence is in `output/evaluation.json`, `output/reproducibility.json` and `output/token_cost_log.json`. The reproducibility report also contains measured usage for the second and third runs; it does not pretend the three-run check cost only one run's calls.

## Independent numeric checks

All three supplied sample examples match to the template's presentation precision:

| Route / week | Cost per tonne-km | vs. history | vs. peers |
| --- | --- | --- | --- |
| Delhi-Jaipur / 2024-11-11 | 4.17 | +35.5% | +21.0% |
| Ahmedabad-Mumbai / 2025-01-20 | 3.29 | +29.5% | +22.5% |
| Mumbai-Pune / 2025-09-15 | 3.98 | +9.2% | +23.6% |

Tests also use small hand-calculated examples rather than only comparing functions to themselves. They cover weighted shipment aggregation, Monday/Sunday cutoffs, current/future exclusion, missing calendar weeks and route-excluding peers. `scripts/verify_numbers.py` separately rebuilds every supplied weekly rate, total, historical/peer baseline and percentage with 50-digit Decimal arithmetic. All 5,096 checks passed within 10⁻⁹; the largest absolute difference was 2 × 10⁻¹¹.

## Grounding checks

- N001 supports Chennai-Bangalore in the February 24 and March 3 weeks. The latter has 81.5% affected tonne-km and 3.7 percentage points of uncovered rise, below the explicit five-point review threshold. Partial exposure is disclosed. March 10 and March 17 are rejected after recovery.
- N002 supports the Ahmedabad-Mumbai January 20 festival week.
- N003 can support a rise consistent with its stated fuel uplift near the effective start. It cannot excuse a much larger rise or a new rise after the step has been absorbed by all historical weeks.
- Unaffected-route and no-rate-change notes fail even when their route/date metadata looks superficially relevant.
- Wrong note IDs, invented quotations, malformed LLM JSON and failed calls fall back to source text without changing any verdict or metric.
- Content-hashed annotations reject changed source notes pending review.
- A tiny affected shipment cannot excuse an uncovered 30% weekly increase. Forged eligibility booleans also fail independently rebuilt citation checks.

## Browser verification

The local demo was checked in a browser: coverage cards, route chart, route filtering, cited festival answer, monthly flooding question, rejected notes and CSV download. The exported file parsed as 728 rows with the correct header. The full review additionally checked that route selection updates the inspector, reversed routes return no unrelated findings, both date-range boundaries apply, and keyboard focus survives table re-rendering. `output/demo_preview.jpg` records the final interface. Calendar-boundary and `to`-phrasing queries are additionally covered by automated regressions.

HTTP integration tests additionally verify asset delivery, results JSON, byte-exact CSV export, questions, invalid requests and rejection of paths outside the served asset allowlist. Mobile breakpoints exist in CSS but were not separately verified in a device viewport.

## Limits of this evidence

The event windows include explicitly documented human interpretations. The thresholds are configurable judgment calls. There is no complete labeled anomaly dataset, no production deployment, and no benchmark of neural embeddings against TF-IDF. The Q&A interface supports constrained route/date/status/note questions rather than unrestricted natural-language reasoning. Local AI was genuinely run for validated extractive quotes and, in version 1.3, grounded answer plans over retrieved findings/notes. Python renders the selected facts; no free-form generated explanation is accepted merely because it cites a valid note.

The full source review is retained in the private working notes. Remaining limits include the conservative question vocabulary, retrospective publication policy, crash-interrupted multi-file commits and checksum trust boundary. Packaging checks the final source/input/label fingerprints and atomically replaces the submission ZIP only after verifying every selected file. Internal audits and competitor research are excluded from the recruiter ZIP.

The saved demo works without a model service. Live Q&A requires an available local model; its mode and fallback are shown. `RAG.md` gives the launch and verification commands; `evidence/rag_verification.json` retains exact prompts/responses and measured usage separately from the full-run batch log.
