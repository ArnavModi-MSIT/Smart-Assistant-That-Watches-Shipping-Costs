# Freight Watch

Shipping-cost monitoring assistant for the FreightTiger case study, built with Python's standard library and HTML/CSS/JavaScript.

## Run

Requires Python 3.10+; no package installation is needed.

```powershell
python -m freight_watch serve --output-dir output
```

Open http://127.0.0.1:8765, or double-click `start_demo.cmd`. The saved demo works offline. To regenerate the CSV and verify three unchanged runs:

```powershell
python -m freight_watch verify --output-dir output
```

## Method

- Group directional routes by the supplied route type and Monday-Sunday weeks.
- Weekly cost per tonne-km = total freight cost / total shipment tonne-km.
- History = mean weekly rate in the preceding eight calendar weeks. Use available prior weeks when fewer than eight exist; leave missing baselines blank.
- Peers = same-week mean for other routes of the same type, excluding the current route.
- Flag a history rise of at least 15%, or a rise of at least 5% with a peer gap of at least 20%. These configurable thresholds are judgment calls.

TF-IDF retrieval ranks context notes. Reviewed route, publication, event-window and impact checks control applicability. Justified rows cite the exact note; unsupported increases remain unexplained.

## Optional local AI

With Ollama running and `qwen3:1.7b` installed:

```powershell
python -m freight_watch verify --output-dir output --llm-model qwen3:1.7b
python -m freight_watch serve --output-dir output --llm-model qwen3:1.7b
```

Qwen selects checked quotes and retrieved facts for questions. Python computes verdicts and renders answers. Temperature is 0, seed is 42, and invalid output falls back to verified facts.

## Validation and deliverables

The supplied data produces 728 route-weeks: 14 unexplained, three justified and 711 normal. Ten authored reference cases and citation checks pass; three unchanged runs match on numbers, flags and note IDs. This small labeled set does not establish accuracy on unseen data.

| Deliverable | File |
| --- | --- |
| Output CSV | [output/output.csv](output/output.csv) |
| Labeled evaluation | [output/evaluation.json](output/evaluation.json), [reference cases](config/labeled_weeks.json) |
| Three-run check | [output/reproducibility.json](output/reproducibility.json), CSV copies in `output/verification/` |
| Full-run token/cost log | [output/token_cost_log.json](output/token_cost_log.json) |
| Ten-minute walkthrough | [WALKTHROUGH.md](WALKTHROUGH.md) |

The recorded AI run used two calls, 215 input tokens, 103 output tokens and one cached reuse. Hosted API charge is USD 0; local hardware/electricity cost is unmeasured. Offline runs make no model calls.
