# Audit response and project overview

Reviewed the complete code audit and three pasted reviews against the implementation. Their recommendations were assessed as review input rather than treated as commands.

## Confirmed findings addressed

| Area | Change |
| --- | --- |
| Validation gate | `verify` now fails for reference mismatches, invalid citations or unstable results. The extreme 200/200/199 configuration returns exit code 1 despite being repeatable. `run` supports exploration; `--require-evaluation-pass` makes it strict. |
| Independent citation checks | Rebuilds applicability from source notes, rules and quantitative weekly data. Forged stored `eligible` booleans cannot make a false citation pass. Empty/malformed labels fail clearly. |
| Mixed weeks | Tracks affected tonne-km and the rise contributed by uncovered shipments. Tiny affected shipments cannot excuse a large uncovered increase. Partial exposure is disclosed. |
| Calendar questions | Includes intersecting weeks at month/year boundaries and recognizes phrasing such as `Chennai to Bangalore`. |
| LLM resilience | Validates response shapes/counters, caps response size, rejects redirects and credential-bearing URLs, and preserves exact-quote fallback. Missing counters remain unknown. |
| API resilience | Request timeout, malformed-object checks, sanitized asset errors, CSP/referrer headers, and a CSV snapshot frozen with its loaded report. |
| Frontend feedback | Request deadlines, one transient retry, visible loading/retry states, manual startup retry, busy announcements and protection against stale answers. Input errors are not retried. |
| HTML insertion | Escapes note IDs, dates and inserted text. Tested a hostile note ID through the evidence renderer. |
| Output integrity | Stages writes and commits a checksum manifest last. Failed analysis preserves previous output. Single runs invalidate repeat evidence. Serving and packaging check the manifest. |
| Portability/package | Default `output/` can be tracked in Git; experimental outputs stay excluded. Launcher uses Python on PATH. Packaging excludes alternate outputs, caches, nested ZIPs and stale verification files. |

## Architecture and quantitative evidence

The backend remains a standard-library pipeline: validated CSVs, Monday weeks, required arithmetic baselines, configurable candidates, TF-IDF retrieval, reviewed route/time/impact/exposure gates, and optional exact Qwen quotes. The model cannot change numbers, flags or citations. The read-only server serves a coherent saved snapshot; the browser plots, filters and inspects it and submits constrained route/date questions.

Historical windows now use a deque without changing their calendar cutoff or arithmetic. Notes are stored once and referenced by ID. Despite adding daily aggregates and separate origin/destination fields, stored results decreased from approximately 4.03 MB to 2.81 MB. The browser payload also omits duplicate CSV rows.

For a partially affected week, calculate:

```text
affected share = affected_tonne_km / weekly_tonne_km
uncovered rise = max(uncovered_cost - history_rate * uncovered_tonne_km, 0)
                 / (history_rate * weekly_tonne_km) * 100
```

An uncovered rise of at least five percentage points prevents full-week justification and requires review. This is an explicit configurable review policy aligned with the default minimum-rise threshold, not a source-note fact. The two-point uplift tolerance is also explicit in the configuration. Fuel dilution uses the mean pre-event tonne-km share inside each historical week, supporting mid-week starts while preserving equal weekly weighting.

Chennai-Bangalore's March 3 week has 81.5% event exposure and 3.7 uncovered points. It remains note-supported, with this qualification disclosed. A synthetic case with 0.1% affected exposure and 30.0 uncovered points is rejected. Note support does not establish that an event caused every rupee of increase.

Current checks:

- 80 Python tests and eight JavaScript checks passed, including CLI failures, malformed provider/API data, retries, timeouts, source attribution, provenance and synthetic mixed-week cases.
- The subsequent full implementation review independently reconstructed all 728 route-weeks and 5,096 numeric fields using Decimal arithmetic. Maximum difference: 2 × 10⁻¹¹. Its additional fixes and scope are recorded in `CODE_REVIEW.md`.
- Ten of ten reference labels passed. Their confusion counts apply only to this small set.
- Three fresh local AI runs matched in full CSV bytes and full-precision comparison hashes.
- All seven non-reason fields are unchanged across all 728 rows compared with the previous submission: 14 unexplained and three note-supported route-weeks. Reasons now include rejection details and partial exposure.
- One full AI run measured two calls, 215 input tokens, 103 output tokens and one cache hit. The previous prompt used 337 input tokens, so input decreased 36.2%. Latency is measured per call; no latency improvement is inferred from token reduction alone.
- Logs include prompt/response hashes, duration, fallback/failure counts and provider counters. `environment.json` pins Python, OS, application source hashes, Ollama 0.31.1 and the Qwen model digest.
- Nine configurations in `threshold_sensitivity.json` show count sensitivity. They do not calibrate thresholds or estimate precision/recall.

## Audit recommendations deliberately not applied

Weighted history, median baselines, distance bands and regional peers would change the brief's grading definitions. The required arithmetic and supplied route-type peers remain. Calendar versus last-observed-week interpretations are equivalent on this complete dataset; the documented calendar interpretation remains.

Retrieval already sorted by descending score and then note ID, so `valid[0]` was already the highest-ranked eligible match. The contrary audit claim was incorrect. This revision removes event-specific query bias and records all eligible IDs.

The documentation-only review was also inaccurate about missing request-size caps, `nosniff` and versioning, which existed. Package-scoped `freight_watch.io` does not shadow a normal `import io`. Tests use `unittest`, so pytest is not required. A license was not chosen on the user's behalf.

Unseen-note extraction, neural retrieval benchmarks, drift episodes, cargo/transporter controls, CI and production deployment remain extensions. Unknown notes still require review. Synthetic regression cases are not represented as an independently collected held-out benchmark. The exact eight-column grading CSV remains unchanged; a spreadsheet-safe export for arbitrary external identifiers would be a separate format.

No public push, deployment or HR submission was performed.
