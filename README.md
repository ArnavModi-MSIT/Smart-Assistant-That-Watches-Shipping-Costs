# Freight Watch

A local Python assistant for the supplied FreightTiger case study. It tracks weekly shipping costs, flags unusual rises, and gives short explanations grounded in the supplied notes.

## Run

Python 3.10+ is the only required dependency. Double-click `start_demo.cmd`, then open `http://127.0.0.1:8765`. The saved demo works offline. To regenerate and serve:

```powershell
python -m freight_watch verify --output-dir output
python -m freight_watch serve --output-dir output
```

`verify` runs three unchanged analyses and exits nonzero if reference checks, citations or reproducibility fail. Stop the demo with Ctrl+C. No model, database or package installation is required for this path.

## How it works

Built with Python's standard library and a small HTML/CSS/JavaScript interface. The pipeline reads the CSVs, groups shipments, computes comparisons, flags candidates, checks note evidence, and exports the requested CSV.

- Preserve directional origin/destination routes and the provided `route_type`.
- Group dates into Monday-Sunday weeks; `week_of` is Monday.
- Weekly cost per tonne-km = `sum(freight_cost_inr) / sum(quantity_tonnes * distance_km)`.
- History = mean weekly rate within the eight calendar weeks strictly before the current week. Use only available observations, report their count, and leave comparisons unavailable when no history exists.
- Peers = mean rate of all other routes with the same `route_type` in that week, excluding the current route. Each route has equal weight.
- Percentage change = `(current / baseline - 1) * 100`; round only for display.

The brief does not prescribe an anomaly threshold. Our transparent default is a history rise of at least 15%, or a rise of at least 5% with a peer gap of at least 20%. These are configurable judgment calls, not a learned accuracy claim.

The CSV follows the supplied header and presentation:

```text
route,week_of,cost_per_tonne_km,vs_own_history,vs_similar_routes,flagged,matched_note_id,reason
```

It contains all 728 route-weeks: 14 unexplained, three note-supported and 711 normal under those defaults. It preserves the sample's `Yes`, `No (justified)` and `No` verdicts; unexplained rows have blank note IDs. The supplied file is named `sample_output_format_v2.csv`; its original malformed comma is preserved, while our export uses proper CSV quoting.

## Optional AI bonus

The existing in-memory TF-IDF retriever ranks the supplied notes. Human-reviewed, content-hashed annotations check exact route, publication time, event window, shipment exposure and stated impact. Unreviewed, expired or nonimpact notes cannot justify a rise. Supporting evidence is a plausible explanation, not proof of causation.

An optional local Qwen model selects an exact sentence from an already eligible note. Invalid output falls back to the original source. The model cannot change arithmetic, flags or citations.

Start an installed Ollama service with `qwen3:1.7b` available:

```powershell
python -m freight_watch verify --output-dir output --llm-model qwen3:1.7b
python -m freight_watch serve --output-dir output --llm-model qwen3:1.7b
```

Q&A is the brief's stretch goal. Ask a directional route and date/month/year, such as `Why Chennai-Bangalore in March 2025?`. It retrieves saved findings and notes using the same retriever. The model selects verified facts in a checked answer plan; Python renders them. Unsupported constraints are rejected. Graph clicks inspect saved findings without inference. See `RAG.md` for the optional trace and commands.

## How we checked it

Ten labeled cases cover the supplied samples, supported events, expired evidence and stable observations. The 98 Python tests cover arithmetic, temporal/citation failures, malformed inputs, model fallback and output handling. Nine frontend checks cover request handling and safe rendering. An independent Decimal reconstruction checks all 728 route-weeks and 5,096 numeric fields. These are regression checks, not general accuracy on unseen data.

```powershell
python -m unittest discover -q
node tests/test_web.js
python scripts/verify_numbers.py --output-dir output
```

`output/evaluation.json` records the reference results. `output/reproducibility.json` and `output/verification/` record three runs with identical flags, citations and numbers; the saved AI run also produced identical full CSVs. `VALIDATION.md` explains the checks and limitations.

## Submission

The ZIP includes working code and inputs, `output/output.csv`, this README, evaluation/reproducibility evidence, the full-run token log and `WALKTHROUGH.md` for the ten-minute Round 2 demo. Build it with:

```powershell
python scripts/package_submission.py
```

Packaging verifies that files match the tested code and inputs. The saved full AI batch measured two calls, 215 input tokens, 103 output tokens and one cached reuse. `output/token_cost_log.json` records actual provider counters and timings. Local Ollama has no hosted API charge; hardware/electricity cost is unmeasured. Offline runs make zero calls. Optional Q&A usage is logged separately in `evidence/rag_verification.json`.
