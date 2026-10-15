# Grounded Q&A in version 1.3

The saved CSV contains deterministic verdicts plus validated local model quote selection. Live Q&A is a separate optional RAG path over the **728 computed findings and ten original notes**. The default demo performs retrieval without a model; it labels that mode explicitly.

## Run real local Q&A

Start an installed Ollama service with `qwen3:1.7b` available, then:

```powershell
python -m freight_watch serve --output-dir output --port 8765 --llm-model qwen3:1.7b
```

For a service running on another loopback port, add `--ollama-url http://127.0.0.1:11435`. No model is bundled or automatically downloaded. Use `--llm-timeout 120` to control the deadline. An unavailable model returns a labeled fallback using verified facts; the demo remains usable. A graph-dot click inspects the saved result and does not trigger a model call. **Ask assistant** triggers retrieval and, when configured, local generation.

Examples:

- `Why Ahmedabad-Mumbai on 2025-01-20?`
- `Why Chennai-Bangalore on 2025-03-10?`
- `Why did Chennai-Bangalore get pricier in March 2025?`
- `What does note N010 say?`
- `Which routes need review?`

## Retrieval and generation contract

1. Parse route direction, ISO date/range, month/year, verdict or exact note ID. Unknown/reversed routes, exclusions, incompatible constraints and unsupported vocabulary fail closed. This is bounded natural-language Q&A, not unrestricted chat.
2. Build source documents from the verified snapshot. Findings contain computed numeric facts/verdicts. Justifications are independently rebuilt against frozen, content-hashed event rules, including publication, route, event exposure and uplift checks. Notes contain their exact text and reviewed window/exclusion. Notes published after the requested scope's last week are excluded.
3. Filter candidate source IDs by the requested scope; rank them with the same TF-IDF cosine retriever used by the core engine, stable source-ID tie breaks, and a maximum of eight retrieved documents. This is a lexical vector index in memory. Similarity alone never establishes applicability.
4. Send the question and retrieved verified facts to the local model. Ollama receives a JSON schema restricting source IDs and fact keys. It generates an ordered answer plan such as:

```json
{"items":[{"source_id":"F:Ahmedabad-Mumbai:2025-01-20","facts":["rate","verdict","history","evidence"]}]}
```

5. Independently validate that each source was retrieved, all requested keys exist, sources/keys are unique, findings include their rate/verdict/evidence/exposure constraints, and notes retain window or nonimpact limitations. A route-week answer must include a finding. When at most five findings are retrieved, include every one so a monthly answer cannot omit its unexplained weeks. Larger scopes retain complete counts and show selected evidence. Reject prose fields and invented fact keys even if a citation ID is valid.
6. Render only the server's selected verified sentences, with source IDs. The model selects and orders facts; **Python renders the English**. We do not claim unrestricted prose generation or a general semantic-entailment model. Verdicts and numbers cannot be changed by an answer plan. An invalid plan or provider failure uses an explicitly labeled deterministic retrieval answer.

Each finding has a stable `F:<directional-route>:<Monday-date>` ID. A standalone original note is source context, not a new justification for every nearby week. An unexplained finding always retains the absence of an eligible cause. Partial support retains its exposure percentage and causal limitation.

## Evidence and cost

```powershell
python scripts/verify_rag.py --llm-model qwen3:1.7b
```

This verifies festival support, expired flooding, partial flooding, a mixed March query containing both supported and unexplained weeks, a nonimpact note, a future festival, reversed direction and an empty requested status. The six valid-scope question requests require **accepted real model plans** when a model is specified; fallback output cannot masquerade as a passing AI check. The two invalid scopes make no model call. A repeated festival question verifies the cache without charging its original tokens again.

`evidence/rag_verification.json` records each question, retrieved sources/scores, expected source/verdict, plan, exact model prompt and response, measured provider counters, duration, response hash and model digest. It includes the verified output-manifest hash and source fingerprints. Packaging refuses stale or failing RAG evidence. The eight authored cases are a small regression set, not general language/retrieval accuracy.

The batch's `output/token_cost_log.json` accounts only for the first full analysis run's quote-selection calls. Q&A has its own usage evidence. Metadata requests are distinct from inference calls. Cache hits report zero new tokens, while original counters remain separately available. Missing provider counters stay unknown. Hosted API charges are USD 0 for this local path; hardware/electricity cost is unmeasured.

The browser's **Retrieved evidence** and **Exact model input and output** expanders show the live trace. UI output is escaped; longer model requests have a provider-aware deadline and avoid automatic duplicate inference retries. Per-process caching resets when the server restarts. Interactive requests are not persisted by the read-only demo server; use the verification script to retain a reproducible trace.

Provider interface: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [chat and counters](https://docs.ollama.com/api/chat). A schema helps constrain output, but the independent validator and executed checks provide the trust boundary.
