# Ten-minute walkthrough

Start the demo with `start_demo.cmd`. The saved run works without an active Ollama service.

## 0:00-1:00 - Problem and scope

"We need to identify unusual route-level freight-cost increases and explain which ones have applicable support in the supplied notes. I analyzed 2,940 synthetic shipments, seven routes and 104 weeks. The main output contains 728 route-week observations."

Point to the coverage cards: 14 unexplained increases and three note-supported increases under the stated thresholds. These are route-week counts, not unique routes.

## 1:00-3:00 - Core mathematics

Use the evidence inspector to show the cost, history and peer baselines. Explain:

- Monday-to-Sunday grouping using the supplied route type.
- Weekly rate equals total freight cost divided by total shipment tonne-km.
- Historical average contains at most the preceding eight calendar weeks; current and future weeks cannot leak in.
- Same-week peers exclude the route itself.

Explain the two threshold branches. The brief did not prescribe a threshold. The peer branch requires some historical rise to avoid flagging permanently expensive routes.

## 3:00-5:00 - Show a justified increase and an expired reason

Click **Festival surcharge**. Ahmedabad-Mumbai, January 20, 2025 shows INR 3.29/tonne-km, +29.5% against history and note N002. Open the original source note. The festival interpretation covers that Monday-to-Sunday week only.

Click **Expired flooding**. The March query includes its boundary-spanning February 24 week, the supported March 3 week, and unexplained March 10 and March 17 weeks. N001 ends March 8. Show March 3's partial exposure: 81.5% of tonne-km, with an uncovered contribution below the explicit five-point review policy. Semantic relevance cannot justify later dates.

## 5:00-6:00 - Show gradual drift

Ask `Why Mumbai-Pune on 2025-09-15?`. The cost is INR 3.98, +9.2% against history and +23.6% against peers. The smaller-rise-plus-peer rule catches it.

N006 is published later and describes stable conditions. N003's May fuel increase is already represented throughout September's historical baseline, so it cannot keep excusing later drift.

## 6:00-7:00 - Explain AI use and guardrails

"I use TF-IDF vector retrieval for ten notes, then apply reviewed scope, date and impact gates. This is an in-memory index; a separate database would add setup without helping at this scale. Unknown notes cannot automatically justify a rise."

"A local Qwen model selects an exact cost-related quote from an already eligible note. The program verifies the quote and attribution. It cannot change the verdict, note ID or numeric comparisons. If its output is invalid, the full source note is used instead."

"Version 1.3 also retrieves computed findings and original notes for questions. When launched with `--llm-model qwen3:1.7b`, Qwen generates a JSON answer plan selecting source IDs and verified fact keys. Python rejects invented facts, wrong-scope sources and omitted limitations, then renders the selected facts. The model does not freely rewrite evidence."

Show **Retrieved evidence** and **Exact model input and output** under an answer. Ask `What does note N010 say?` to show that a source note can be retrieved while its no-rate-change limitation remains explicit. The default saved demo labels retrieval-only mode. Event annotations are human-reviewed, and language constraints remain conservative.

## 7:00-8:30 - Demonstrate trust and repeatability

Open `output/evaluation.json`: ten labeled examples, including the supplied samples and the expired-flood case. Explain that this is a small reference set rather than a complete measure of accuracy.

Open `output/reproducibility.json`: three unchanged runs, matching stable fields, full precision and full CSV hashes. Explain that a failed reference evaluation now returns nonzero even when wrong outputs repeat. `tests/test_audit_regressions.py` reproduces that defect and tests partial-event failures. Temperature 0 is a setting, not proof.

Mention the 98 Python tests, nine frontend checks and the separate Decimal reconstruction of all 728 route-weeks. `evidence/rag_verification.json` records seven authored Q&A cases, including five real model calls and a cache check. `CODE_REVIEW.md` and `COMPETITOR_REVIEW.md` record the reviews. Packaging checks that source code, input hashes and Q&A evidence match the verified run.

## 8:30-9:30 - Cost and packaging

Open `output/token_cost_log.json`: two local calls, 215 input tokens, 103 output tokens and one cache hit. The original larger prompt used 337 input tokens. Show call timings, source hashes and model digest; caching is per run. Hosted API cost is USD 0, electricity/hardware are unmeasured, and failed counters stay unknown.

Click **Export CSV**. Explain the exact schema, blank IDs for unexplained rows and proper quoting, including the malformed comma in the supplied template that was preserved unchanged.

## 9:30-10:00 - Limitations and next step

"The thresholds are explicit judgment calls. Route-level aggregation does not control for material or transporter mix. A rolling baseline can absorb long gradual drift. The reviewed annotations work for these supplied notes, and new context needs review. The next extension would be a larger labeled set and structured event ingestion, then testing neural retrieval against the lexical baseline."

Keep questions focused on reproducible evidence and trade-offs. Do not claim that every flagged route is overcharging or that the notes establish causation.
