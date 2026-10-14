# Freight Watch

A local assistant that spots unusual weekly freight-cost increases, retrieves the supplied context notes, and distinguishes note-supported increases from unexplained ones. Built for the FreightTiger Software Engineering Intern (AI) case study.

## Run the demo

Python 3.10 or newer is the only required dependency. No pip packages, API key or internet connection are needed for the saved demo or the deterministic pipeline.

On Windows, double-click `start_demo.cmd`, or run:

```powershell
.\start_demo.ps1
```

Open `http://127.0.0.1:8765`. Press Ctrl+C in the terminal to stop the server. The launcher serves the saved output; if it is missing, it first regenerates an offline analysis. If PowerShell execution policy prevents the launcher from running, use the Python commands below. No system policy change is required.

```powershell
python -m freight_watch verify --output-dir output
python -m freight_watch serve --output-dir output --port 8765
```

The demo includes a route chart, history and peer comparisons, verdict filters, a note inspector, CSV export, and constrained natural-language questions. Examples:

- `Why did Chennai-Bangalore get pricier in March 2025?`
- `Why Ahmedabad-Mumbai on 2025-01-20?`
- `Why Mumbai-Pune on 2025-09-15?`
- `Which routes need review?`

The question endpoint reads computed findings. It does not call an LLM or pretend to answer unrelated questions. Month queries, including abbreviations such as `Sep`, must include a year because the input covers two years. ISO dates are mapped to their Monday week; `between 2025-03-03 and 2025-03-17` includes both boundary weeks. Month/year requests include weeks intersecting that calendar period, even when their Monday is in the preceding month/year. Routes can be written as `Chennai-Bangalore` or `Chennai to Bangalore`. Unknown/reversed routes, conflicting periods, exclusions and unsupported filters return no findings. Explicit unexplained/justified/normal status constraints are honored.

## Deliverables

`output/` contains the saved, locally executed AI run:

| File | Purpose |
| --- | --- |
| `output.csv` | All 728 route-weeks, with the exact eight-column output contract |
| `results.json` | Full precision metrics, historical weeks, retrieved notes and rejection reasons used by the demo |
| `run_summary.json` | Coverage, thresholds, input hashes and counts |
| `token_cost_log.json` | Actual model calls, token counters and cost basis for the first full run |
| `evaluation.json` | Ten explicitly labeled reference cases and source-citation checks |
| `reproducibility.json` | Three-run hashes and call logs for each run |
| `verification/run_2.csv`, `verification/run_3.csv` | The other two untouched-run outputs |
| `run_manifest.json` | Committed file hashes and strict verification status |
| `environment.json` | Python/OS, application source hashes, Ollama version and model digest |
| `threshold_sensitivity.json` | Counts under nine documented threshold configurations, without accuracy claims |

`WALKTHROUGH.md` provides a ten-minute demo outline. `VALIDATION.md` records what was verified. To build the submission ZIP:

```powershell
python scripts/package_submission.py
```

Packaging refuses an exploratory or failed bundle, verifies committed output hashes, and checks that code, inputs, rules and reference labels match the verified run. It builds a temporary ZIP before atomically replacing the deliverable. `AUDIT_RESPONSE.md` covers the supplied audits; `CODE_REVIEW.md` records the full implementation review, reproduced defects and executed checks. Default `output/` can be tracked in Git; alternate `output-*` folders are experiments and are excluded from the clean ZIP.

Send `FreightWatch_Submission.zip` or a repository link to HR before the scheduled Round 2 slot. The supplied brief does not state an actual date or time. The program does not submit anything.

## Exact core calculations

1. Keep origin-to-destination direction and the supplied `route_type`; do not infer Short/Medium/Long from distance.
2. Assign each shipment to the Monday of its Monday-to-Sunday week.
3. For each route-week, calculate `sum(freight_cost_inr) / sum(quantity_tonnes * distance_km)`. This weights individual rates by transport work and reproduces the sample numbers. Do not multiply summed quantities by summed distances or average individual shipment rates.
4. Historical baseline: arithmetic mean of the route's observed weekly rates inside the eight **calendar weeks strictly before** the current week. With fewer observations, use only those available and report the count. Missing weeks are not padded or pulled from older periods. No history yields an unavailable comparison and no claim of a rising trend.
5. Peer baseline: arithmetic mean of the other routes' weekly rates for the same week and `route_type`, excluding the route itself. Route averages are equally weighted. No peers yields an unavailable comparison.
6. Percentage difference: `(current_rate / baseline - 1) * 100`. Calculate and classify using full precision; round only the exported presentation.

The CSV contract is:

```text
route,week_of,cost_per_tonne_km,vs_own_history,vs_similar_routes,flagged,matched_note_id,reason
```

`cost_per_tonne_km` is numeric text with two decimals. The comparison fields are formatted percentage strings with one decimal and the wording shown in the sample. Although the brief describes these as numeric comparisons, the actual template uses strings; the CSV follows that template, and raw numeric values remain available in `results.json`.

`flagged` uses the sample's `Yes`, `No (justified)`, and `No` conventions. `matched_note_id` is blank for unexplained and normal rows. Rows with unavailable baselines contain explicit `N/A` text rather than misleading zero comparisons. The output contains normal observations too, so the full weekly tracking can be inspected.

## Anomaly rule and its trade-offs

The brief gives exact baselines but no anomaly threshold. The defaults are a transparent judgment call:

```text
candidate = history_rise >= 15%
         OR (history_rise >= 5% AND peer_difference >= 20%)
```

The first branch catches abrupt increases. The second catches smaller rises on routes that are also expensive relative to peers, including the supplied Mumbai-Pune drift example. A positive peer gap alone is insufficient because different routes can have structurally different prices. A current rate above its past average is the operational definition of a rise; a strictly positive week-to-week change is not required.

The thresholds are configurable:

```powershell
python -m freight_watch run --history-threshold 15 --peer-threshold 20 --minimum-rise 5 --output-dir output
```

They are not a learned detector or an official grading threshold. There is no complete labeled ground truth for precision or recall. Small persistent rises, gradual drift after the rolling baseline catches up, and differences in cargo or transporter mix may remain undetected. Those are limitations of this short, route-level case study rather than evidence of wrongdoing by a transporter.

## Retrieval, AI and grounding

`retrieval.py` builds normalized TF-IDF vectors from the ten supplied notes, including word bigrams to preserve route names, and ranks them by cosine similarity. This is an in-memory vector index, not a hosted vector database or a neural embedding model. All ten notes are checked after ranking: a fixed top-k cutoff must not hide applicable nationwide context.

Ranking retrieves candidates; it cannot prove a justification. `config/note_rules.json` contains human-reviewed route, impact and event-window annotations. These annotations are explicit and content-hashed against the original note text, date and scope. If a reviewed note changes, the run fails and requests annotation review. Unknown notes cannot automatically justify an increase.

An eligible justification requires all of:

- The exact route, or an applicable `All Routes` note.
- Publication by the end of the analyzed week, with at least one shipment date inside the reviewed event window. A note published later in that same week may describe earlier event exposure; this is retrospective weekly analysis.
- Quantitative event exposure: affected tonne-km is measured. Uncovered shipments must not independently contribute at least five percentage points of weekly rise. This configurable review policy is disclosed rather than represented as a source-note fact.
- A source statement supporting increased cost. Unaffected routes, unchanged prices, stable demand and recovery announcements do not qualify.
- An event that is not already included throughout the historical baseline.
- A rise consistent with a stated magnitude, when the note provides one.

Reviewed event interpretations:

- **N001:** flooding applies February 24 through March 8, 2025. March 9 recovery ends its applicability. A week containing March 9 is supported only if it has affected shipment dates before recovery.
- **N002:** `festival week` means January 20-26, 2025, the Monday-to-Sunday week of the note. This is an explicit interpretation, not an independently supplied date range.
- **N003:** diesel costs increase starting May 5, 2025, with no end specified. The event cannot explain a fresh rise once every historical week already includes it. Its 7% upper stated uplift is multiplied by the mean pre-event tonne-km share inside each historical week, with an explicit two-percentage-point review tolerance. It does not fully justify a 30% increase. Both exposure and tolerance policies are in `config/note_rules.json`; see the worked mixed-week example in `AUDIT_RESPONSE.md`.
- **N004-N010:** do not support an increased freight price. N009 additionally corroborates recovery from the earlier flood.

Supporting notes establish a plausible recorded explanation, not a causal proof or an exact estimate of rupees attributable to an event. For events without a numerical uplift, no quantitative ceiling is invented.

### Optional local LLM

The saved AI run used the already installed `qwen3:1.7b` model through Ollama. To regenerate that path, start your installed Ollama service, ensure that model is available, and run:

```powershell
python -m freight_watch verify --output-dir output --llm-model qwen3:1.7b
```

For a different loopback port, pass `--ollama-url http://127.0.0.1:11435`. The port used during development was temporary; it is not a service dependency of the saved demo. No models are bundled or downloaded by the application. An unavailable model falls back to the full source note and records the failed call.

For each distinct **already eligible** cited note, the LLM selects an explanatory quote. The output must be valid JSON, identify the same note and copy complete cost-related sentences exactly from the source. Fragments dropping a leading negation, incorrect attribution, invented text and malformed output are rejected. The final explanation combines that extract with deterministic verdict, dates and coverage. The model never calculates costs, chooses flags or changes note IDs. Identical notes are cached within each run, so the 728-row analysis needs only two calls for its two distinct cited notes.

This is deliberately bounded retrieval-assisted generation. It gives the AI a narrow extractive task and keeps the auditable decision separate. Broad free-form generation and LLM-based date extraction were avoided because ten short notes can be reviewed directly and the challenge penalizes fabricated reasons. Settings: temperature 0, seed 42, thinking disabled, maximum 160 generated tokens. These settings alone are not a reproducibility guarantee; the three-run comparison provides the evidence.

Ollama API references: [chat and token counters](https://docs.ollama.com/api/chat), [model digests and details](https://docs.ollama.com/api/tags). Inference uses `/api/chat`; separate metadata requests record the installed version/model digest. No embedding API calls are made. Per-call logs retain durations and prompt/response hashes without storing a second copy of the source text.

## Validation and operating cost

```powershell
python -m unittest discover -v
node tests/test_web.js
python -m freight_watch verify --output-dir output-offline
python scripts/verify_numbers.py --output-dir output
```

The server tests bind a temporary loopback port. Restricted execution sandboxes may require approval for those socket operations; a normal local Python session needs no special configuration.

The 80 Python tests cover core arithmetic, mixed-week adversarial cases, retrieval edge cases, malformed model/API data, CLI failure gates, ambiguous routes, numeric range boundaries, query constraints and artifact provenance. Eight Node checks cover retries, deadlines, hostile-ID rendering, calendar spacing and route selection; Node is a developer-test dependency only. An independent 50-digit Decimal reconstruction checks all 728 route-weeks and 5,096 numeric fields against the raw input. The ten reference labels remain manually authored cases from supplied examples, event windows and stable observations. Their confusion counts and the synthetic regression cases do not establish general accuracy on unseen routes or events.

`verify` starts three independent analyses without changing inputs. It compares all CSV fields except `reason`, full-precision metrics and input hashes, and records whole-CSV identity. It returns nonzero if any reference case or independently rebuilt citation check fails, even if wrong outputs repeat perfectly. A single `run` replaces repeat evidence with `not_run`; use `--require-evaluation-pass` to gate an exploratory run. `--rules` and `--labels` support separately reviewed context and reference sets. Writes are staged with a checksum manifest committed last, and the server refuses a damaged or strictly failed bundle.

The shipped full AI run measured **2 calls, 215 input tokens and 103 output tokens**, plus one cached quote reuse. Removing redundant prompt fields reduced input from the original run's 337 tokens by 36.2%. Latency is measured separately and no speed claim is inferred from token reduction. Hosted API cost is **USD 0**; local hardware/electricity costs were not measured. Failed calls without counters remain `null`. Offline mode makes zero calls. Reproducibility incurs additional calls, recorded per run. CLI/UI status distinguishes accepted quotes from failures or source fallbacks; `--llm-timeout` controls the provider deadline.

## Supplied-file issue

The PDF refers to `sample_output_format.csv`; the actual file is `sample_output_format_v2.csv`. Its final example has an unquoted comma inside the `reason` field, producing nine fields under an eight-column header. The original is preserved unchanged. We use the intact header as the contract and Python's CSV writer for proper quoting. The three illustrative comparisons are separately checked against the supplied shipment data.

Inputs are validated for required fields, unique shipment IDs, valid ISO dates, finite positive quantity/distance/cost and transport work, recognized route types and consistent route-type assignment. Route names are treated as supplied directional identifiers. Ambiguous hyphen-separated origin/destination combinations are rejected rather than silently merged; raw results retain origin and destination separately.

## Code layout

- `engine.py`: weekly metrics, baselines, anomaly classification and output rows.
- `evidence.py`, `retrieval.py`: source-grounded event checks and ranked retrieval.
- `llm.py`: loopback-only optional LLM, quote validation, cache and measured token log.
- `questions.py`, `server.py`, `web/`: read-only local demo and conservative query interface.
- `io.py`, `models.py`: input validation, data types and CSV contract.
- `bundle.py`, `scripts/`: verified artifact snapshots, independent numeric audit and safe submission packaging.
- `evaluation.py`, `tests/`: labeled evaluation and independent boundary/guardrail checks.

The server is intended for a local interview demo and binds to `127.0.0.1`. It has no upload, write or application-submission endpoints. It is not a production deployment.
