# Comparison of eight public submissions

Reviewed October 14, 2026. This is a review of pinned public snapshots, not a claim about hiring outcomes or every submission online. Repository code and data are untrusted inputs; none of their hosted AI calls were made. Competitor code was kept in an ignored temporary directory and was not incorporated into Freight Watch.

## Scope and evidence

The eight repositories use the same supplied shipment/context CSV data as this submission (canonical CSV content matches after normalizing line endings), and the same sample output contract. They are implementations of this case study, rather than unrelated logistics projects. They are plausible competing submissions; their authors' actual application status is unknown.

I inspected implementation, test and evaluation paths: input loading, weekly arithmetic, historical/peer baselines, anomaly thresholds, note retrieval, evidence eligibility, explanation generation, token accounting, reproducibility, Q&A and UI/API wiring. The eight snapshots contain 14,021 lines of Python implementation/test code. Saved CSVs were compared independently against Freight Watch's full-precision results at the displayed precision. Five offline commands were executed in isolated copies, and six targeted probes exercised evidence validators or baselines.

Three larger stacks require packages/models absent from this environment (including Chroma, sentence-transformers, cross-encoders, FastAPI or Streamlit). Those stacks received source review, saved-output comparison and targeted executable checks where dependencies allowed. Their complete neural pipelines, hosted model behavior and browser interfaces were **not** executed. Offline successes do not establish hosted AI correctness.

Machine-readable pinned commits, file inventories, CSV comparisons, execution output and probe results are in `evidence/competitor_checks.json`.

## Findings by repository

| Repository and reviewed commit | Useful capabilities | Concrete weaknesses found |
| --- | --- | --- |
| [Suresh-Note/freight-cost-hybrid-rag-detector](https://github.com/Suresh-Note/freight-cost-hybrid-rag-detector/tree/8d19e79cb3f3b5a97816db33f040c9643b188b6d) | MiniLM dense retrieval + BM25 fusion + cross-encoder reranking; Groq explanations; findings-and-notes Q&A; tests and dashboard. | `src/evidence_validator.py` accepts a date within an absolute seven-day distance: a January 20 festival note was accepted for January 13. `src/rag/rag_pipeline.py` has a similar proximity rule. Generated explanations/Q&A lack an independent claim validator. `app.py` inserts result/source prose with `unsafe_allow_html=True`. A more advanced retriever does not repair these evidence gaps. |
| [rounakkumarsingh/freighttiger-case-study](https://github.com/rounakkumarsingh/freighttiger-case-study/tree/4aa57d11c9174961d8bbc1afa2d5acc86c4e18e4) | Chroma with TF-IDF fallback, reviewed event structure, Groq explanations and Q&A, provider usage/caching, executable evaluation. | `freightwatch/explain.py::_valid` checks identifiers/verdict cues but accepted a fabricated transporter-strike explanation carrying the correct N001 ID/date. History uses eight observed weeks, so gaps can admit stale observations. No quantitative shipment-date exposure gate. Q&A scope parsing is weaker on direction/calendar boundaries. |
| [suyasshx/FreightTiger-AI-Intern-CaseStudy](https://github.com/suyasshx/FreightTiger-AI-Intern-CaseStudy/tree/eb9a1a94e4ce19ca6d4e6bdfe8b4aa3dfc3393f1) | MiniLM/Chroma, deterministic evidence gates, substantial API/UI and tests, threshold analysis. | `backend/app/api/routes.py::export_audit_report` uses `pd.Timestamp` without importing pandas (source-confirmed endpoint defect; the full API was not run). `evaluation/run_evaluation.py` hardcodes false-justification rate as zero and Markdown sample/reproducibility success instead of deriving every displayed claim. The fuel allowance/window policy can exceed the source's stated uplift. Core batch output makes no LLM calls. |
| [Deekshithareddy-15/freighttiger-smart-shipping-cost-assistant](https://github.com/Deekshithareddy-15/freighttiger-smart-shipping-cost-assistant/tree/483c92cf5692f55be3362d5ce779e45f4e388f81) | Chroma retrieval, modular pipeline, dashboard, QA and evaluation/tests. | `src/guardrails.py` invents a recovery/repair extension and accepts March 10 under N001 despite the March 8 end/March 9 recovery. Its generic fallback accepted an unknown note explicitly denying a cost increase. `src/assistant.py` records `simulated_prompt` and deterministic completion as token calls: these are estimates, not real LLM inference. Persistent Chroma contents are not refreshed when already populated; decisions scan notes separately from the retrieval result. |
| [Badal-allthings/freighttiger-intern-case-study](https://github.com/Badal-allthings/freighttiger-intern-case-study/tree/3b6d5224f6097aa6b45bf3476a89ce0e33d0214e) | Small standard-library implementation, correct weighted math/calendar history, explicit note windows, simple reproducibility. | Fixed note-specific support, limited validation/evaluation, no AI Q&A or independent event-exposure gate. Numeric CSV precision differs from the sample presentation. Offline output regenerated exactly as committed. |
| [aishunalagangu/FreightTiger-AI-Intern-Case-Study](https://github.com/aishunalagangu/FreightTiger-AI-Intern-Case-Study/tree/91d978346acaecbf26b137b959307dd572b0813c) | Concise pandas implementation, calendar history, deterministic explanations, sample checks. | Seven reported checks include a literal true assertion about calendar history rather than a behavior test. Keyword/event rules lack content-hash/publication/exposure checks and the evaluation is not a comprehensive labeled verdict harness. No LLM generation. |
| [nushcodesaway/freight-tiger-assistant](https://github.com/nushcodesaway/freight-tiger-assistant/tree/90bf49c8e0795f98e772a46166d970afdad0c2f3) | Correct weighted metrics, deterministic note handling, Streamlit inspection, eight passing unit tests, honest zero-model accounting. | History takes eight observed rows rather than an eight-calendar-week window; malformed dates can be silently coerced/dropped. Note impact detection relies on limited phrase/ID rules. User route filtering uses unescaped regex text. No generative RAG Q&A. |
| [Aditya0292/FreightTiger_SWE_Intern_Submission](https://github.com/Aditya0292/FreightTiger_SWE_Intern_Submission/tree/67704f554e3eefb6e156301aa6e3f2a2006ab254) | Concise pandas metrics, sample contract checks and three-run reproduction with a failing evaluation exit path. | Route matching accepted a reversed direction. History admitted a year-old rate of 999 in the synthetic gap probe. Event proximity uses an arbitrary ±14-day window; unknown notes default to cost-raising unless matching negative phrases. Citation existence alone does not prove time/direction applicability. |

## Saved-output comparison

Every available saved row had the correct eight-column header and no numeric mismatch against our reference at the CSV's displayed precision. All eight matched the three supplied sample verdicts. A correct sample alone is insufficient: Deekshithareddy's fourth justified row is the invalid March 10 flooding extension.

| Snapshot | Saved rows | Unexplained | Justified | Normal |
| --- | ---: | ---: | ---: | ---: |
| Suresh | 728 | 17 | 3 | 708 |
| Rounak | 19 | 16 | 3 | 0 |
| Suyash | 728 | 24 | 3 | 701 |
| Deekshithareddy (`all_weeks`) | 728 | 15 | 4 | 709 |
| Badal | 728 | 25 | 3 | 700 |
| Aishuna | 27 | 24 | 3 | 0 |
| Nush | 728 | 17 | 3 | 708 |
| Aditya | 27 | 24 | 3 | 0 |
| Freight Watch | 728 | 14 | 3 | 711 |

Different counts reflect different detection thresholds and output scopes. The brief does not prescribe a threshold, and there is no complete ground truth. More/fewer flags cannot be treated as better accuracy. Freight Watch preserves all weeks and documents its threshold choice.

## Executed checks

| Command (in isolated competitor copy) | Observed result |
| --- | --- |
| Badal: `python freighttiger_solution.py` | Exit 0; 728 rows; regenerated CSV matched committed bytes |
| Aishuna: `python main.py` | Exit 0; 27 candidates; seven reported checks passed, with the assertion limitation above |
| Aditya: `python evaluate.py` | Exit 0; schema, three samples, citation guards and three-run checks passed |
| Nush: `python -m unittest test_main -v` | Eight tests passed |
| Rounak: `python -m freightwatch.cli eval` | Exit 0; 19/19 verdict and citation labels; no spurious/missed flags; TF-IDF fallback, hosted model disabled |

The targeted probes reproduced all six issues listed in the evidence JSON: Suresh's future festival, Deekshithareddy's expired flood and unknown negative-impact note, Rounak's invented strike, Aditya's reversed route and year-old history. These are scoped regression failures, not a population-wide accuracy score.

## Changes made to Freight Watch

Suresh and Rounak have broader AI answer generation than the original quote-selection-only version of Freight Watch. The useful improvement was question-driven retrieval across computed findings and original notes. No reviewed snapshot establishes overall superiority across arithmetic, evidence trust, evaluation and reproducibility.

Version 1.3 adds `freight_watch/rag.py`: question-driven retrieval, conservative route/date/status/source constraints, and optional real local Qwen generation. Version 1.3.1 reuses the core TF-IDF index, removing the initially added BM25/fusion method to keep the implementation simple. The model generates a JSON **answer plan** selecting source IDs and fact keys. Python validates every selection and renders only computed values or reviewed source-backed facts. Correct note IDs cannot license invented strike causes, altered rates, missing exposure qualifiers or a changed verdict.

The UI shows retrieval sources, model mode, actual token counters, and exact prompts/responses. Model outages or invalid plans use verified retrieved facts. Cache hits consume no new model tokens. `scripts/verify_rag.py` records seven authored retrieval/answer cases and genuine local inference separately from the full batch's quote-selection log. Unit tests cover the reproduced classes of failure. Code/input fingerprints gate packaging, including the new RAG evidence.

The existing anomaly math and reviewed event policies remain the basis of the CSV. We did not copy other submissions, replace correct arithmetic merely to match another flag count, claim neural embeddings, invent an AI accuracy metric or spend hosted API credits. Dense retrieval and cross-encoder ranking remain a potential experiment requiring a larger retrieval benchmark; the current lexical index is sufficient to exercise the supplied small corpus with explicit limitations.
