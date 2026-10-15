# Ten-minute walkthrough

Start the saved demo with `start_demo.cmd` or `python -m freight_watch serve --output-dir output`.

| Time | Demonstration |
| --- | --- |
| 0:00-1:00 | Explain the task and inputs: 2,940 shipments, seven routes, 104 weeks and 728 route-weeks. Show the coverage cards. |
| 1:00-3:00 | Show weekly weighted cost per tonne-km, prior eight-week history and same-week peers. Explain route exclusion, partial history and the configurable flag thresholds. |
| 3:00-5:00 | Inspect Ahmedabad-Mumbai on January 20, 2025: INR 3.29/tonne-km, +29.5% versus history, supported by N002. Then show Chennai-Bangalore on March 10: flooding note N001 ended March 8, so the rise remains unexplained. Show March 3's partial shipment exposure and its stated limitation. |
| 5:00-6:00 | Inspect Mumbai-Pune on September 15: INR 3.98, +9.2% versus history and +23.6% versus peers. Explain why the earlier fuel step is already included in history. |
| 6:00-7:00 | Explain TF-IDF retrieval and reviewed route/date/impact checks. Demonstrate a route/month question. The default demo uses retrieved verified facts; with local Qwen enabled, show its checked answer plan and exact model trace. |
| 7:00-8:30 | Open `output/evaluation.json` and the ten reference labels in `config/labeled_weeks.json`. Show `output/reproducibility.json` and its three matching runs. Explain that these checks support the submission without establishing general accuracy. |
| 8:30-9:30 | Show `output/token_cost_log.json`: two actual local model calls, 215 input tokens, 103 output tokens and one cache hit. Explain the zero hosted API charge and unmeasured local compute cost. Export the CSV. |
| 9:30-10:00 | Discuss trade-offs: explicit thresholds, human-reviewed note windows, limited question vocabulary and route-level aggregation that does not control for cargo or transporter mix. Evidence supports a plausible explanation, not proof of causation. |

To demonstrate live Qwen answers, launch the server with an available Ollama model:

```powershell
python -m freight_watch serve --output-dir output --llm-model qwen3:1.7b
```
