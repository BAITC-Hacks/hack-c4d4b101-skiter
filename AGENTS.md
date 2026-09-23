# AGENTS.md — «Аким на 5 часов» (Astana Quality of Life simulator)

Instructions for AI coding agents (Codex) working in this repository. Read this whole file before making changes.

## 1. What we are building

A web simulator where a team gets a fixed virtual budget (100 units) and 5 synthetic city districts, makes exactly 5 decisions from a catalog of 14 measures, and receives the **Astana Quality of Life Score** plus an AI explanation.

The core principle: **a deterministic engine computes every number; the LLM only explains, advises and never produces a number on its own.**

Our differentiators (build these after the must-haves work):

1. **Score in context** — after submission, show the plan's percentile among all 694,395 valid plans, its rank, the gap to the best possible plan, and the single change that closes most of that gap.
2. **Verified AI** — the LLM cannot write numbers directly; it references facts by placeholder, and the server fills in values from the simulation. The advisor agent tests every proposal with the simulator before showing it.
3. **Human units** — explanations use real-world units ("school places cover 74% of the norm"), not only 0–100 points.
4. **Stress test** — each plan is run against 7 city events; the result is shown as a separate resilience metric.

## 2. Source of truth (read-only)

The `spec/` folder is frozen. **Never edit any file in `spec/`.** If a task seems to require it, stop and ask.

| File | Role |
| --- | --- |
| `spec/city_dataset.json` | The only data source for the app: rules, indicators, districts, measures, synergies, incompatibilities, events. Text fields are in Russian. |
| `spec/test_cases.json` | Golden answer key: 19 plans with expected score or expected error code. |
| `spec/reference_scoring.py` | Reference implementation of validation, scoring and events. Run `python spec/reference_scoring.py` → must print `19/19 passed`. |
| `spec/Датасет_районов_расширенный.docx` | Human-readable spec for the jury. Do not parse it; the JSON contains the same data. If the JSON and the doc ever seem to disagree, stop and ask. |

Rules about these files:

- The app loads data **only** from `spec/city_dataset.json`. No district names, measure IDs, costs, weights or effects may be written into application logic.
- The app **never reads** `spec/test_cases.json` to produce results. Only tests read it.
- If a golden test fails, the bug is in our code. Never change expected values to make a test pass.

## 3. Non-negotiable rules

1. **Do not change the scoring formula, rules or data.** Score = `0.7 × D_avg + 0.3 × min(D_d) − 1.0 × N_crit` exactly as in `spec/reference_scoring.py`.
2. **Budget is enforced on the server.** The UI may disable options, but the backend must reject any over-budget plan with `OVER_BUDGET`.
3. **The LLM never computes or invents numbers.** Every number shown to the user comes from the engine (see §8).
4. **The official score is never modified by events.** Event results live in a separate `stress_test` object. Buying an event response is allowed only from unspent budget (`100 − plan cost`) and affects only the stress-test result.
5. **Do not reveal the optimum before submission.** Percentile, rank, best-possible score and gap are returned only by the submit endpoint, never by preview endpoints.
6. **Works without an API key.** If no LLM key is set, every AI feature falls back to deterministic templates, and the app still runs end to end.
7. **Determinism.** The same plan always gives the same score, for any team, at any time. No randomness in the engine.
8. **Secrets** go in `.env` (git-ignored). Commit only `.env.example`.

## 4. Tech stack

- Python 3.11+
- Backend: FastAPI + Pydantic v2, served by uvicorn
- Frontend: Streamlit (calls the backend over HTTP)
- Storage: SQLite for the leaderboard
- Numerics: numpy (for the solution-space cache)
- Tests: pytest
- LLM: any OpenAI-compatible chat API configured by env vars `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Wrap it in one module so the provider can be swapped.
- Run: `docker compose up` (backend + frontend), plus documented local commands.

Code, identifiers and comments in English. All user-facing UI text and LLM output in Russian.

## 5. Repository layout

```
AGENTS.md
README.md
.env.example
docker-compose.yml
spec/                       # read-only, see §2
backend/
  app/
    main.py                 # FastAPI app and routes
    config.py               # env settings
    engine/
      dataset.py            # load + validate city_dataset.json into typed models
      validator.py          # plan validation, error codes
      simulator.py          # score, district scores, criticals, contributions
      units.py              # score deltas → natural units
      space.py              # solution-space enumeration + cache, percentile, best single swap
      events.py             # stress test
    ai/
      llm.py                # OpenAI-compatible client + no-key fallback
      facts.py              # build the fact table from a simulation result
      explainer.py          # explanation with fact placeholders
      advisor.py            # tool-using advisor agent
    storage.py              # SQLite leaderboard
  tests/
frontend/
  app.py                    # Streamlit UI
scripts/
  precompute_space.py       # builds the solution-space cache
```

## 6. Data model (`spec/city_dataset.json`)

- `rules`: `budget`, `decisions_exact`, `max_per_direction`, `horizon_quarters`, `critical_threshold`, `critical_penalty`.
- `indicators[]`: `code` (T1…C2), `direction`, `name`, `weight`, and `raw` with `formula` and `raw_per_score_point` for converting a score delta to real units.
- `districts[]`: `id`, `name`, `pop_share`, and `indicators` (the 0–100 values used in scoring). Also `raw_indicators`, `passport`, `context_indicators`, `profile` and `key_issues`, which are for display and AI context only and never enter the score.
- `measures[]`: `id`, `direction`, `name`, `type` (`district` | `city`), `cost`, `lag`, `realized_share`, `effects`. Also `effects_natural_units_full`, `description`, `risks` and `opex_per_year`, which are display-only.
- `synergies[]`: `pair`, `indicator`, `bonus`. The bonus applies in the district of the first measure of the pair, or to all districts if that measure is city-wide. It is not scaled by lag.
- `incompatibilities[]`: `pair`, `scope` (`any` | `same_district`).
- `events`: `rules` plus `catalog[]` with `impacts`, `mitigations` (optional `indicators` filter) and a `response` {`cost`, `reduction`}.

Plan format everywhere (API, tests, storage):

```json
[{"measure": "M7", "district": "nura"}, {"measure": "M12", "district": null}]
```

## 7. Engine

Port the logic of `spec/reference_scoring.py` into `backend/app/engine/` as clean, typed, dataset-driven code. The results must be identical.

**Validation** returns the first violation, checked in this order, with these codes:

1. `WRONG_COUNT` — not exactly 5 measures
2. `UNKNOWN_MEASURE`
3. `DUPLICATE`
4. `DISTRICT_REQUIRED`, `DISTRICT_NOT_ALLOWED`, `UNKNOWN_DISTRICT`
5. `OVER_BUDGET`
6. `DIRECTION_LIMIT` — more than 2 in one direction
7. `INCOMPATIBLE`

Also return a Russian message, `cost` and `remaining`.

**Simulation** returns:

- `score`
- `d_avg`
- `district_scores`
- `weakest_district`
- `critical` — list of (district, indicator) pairs below 40
- `indicators_before` / `indicators_after`
- `contributions` — per measure, district and indicator, including synergies
- `cost` and `remaining`
- natural-unit before/after for every changed indicator

Compute in float; round to 2 decimals only for display.

**Natural units**: `raw_after = raw_before + (score_after − score_before) × raw_per_score_point`. This is exact while values stay inside 0–100. Format with the indicator's unit.

**Solution space (`space.py`)**:

- 14 measures expand to 54 options (district measures × 5 districts + 4 city measures).
- All 5-combinations give 3,162,510 candidates, of which **694,395 are valid**.
- Enumerating in pure Python takes about 50 s, so precompute with `scripts/precompute_space.py`. Save the sorted scores to `backend/app/cache/space_<dataset_sha256[:12]>.npy`, load it at startup, and rebuild automatically if the dataset hash changes.
- Provide:
  - `percentile(score)` = share of valid plans with a strictly lower score × 100
  - `rank(score)` = 1 + number of plans with a strictly higher score (tolerance 1e-9)
  - `best_score`
  - `best_single_swap(plan)` = the valid plan reachable by replacing one measure, or changing one measure's district, with the highest score

**Events (`events.py`)**: `stress_test(plan, buy_responses: set[str])` runs all 7 events and returns, per event, the score after the event, the change versus the official score, the number of criticals, which mitigations fired, and whether a response was bought. Also return the average and the worst case. Never overwrite the official score.

## 8. AI layer

**Facts table (`facts.py`).** From a simulation result, build a dict of `fact_id → formatted string`. Examples: `score`, `score_delta_vs_base`, `district.nura.score_after`, `district.nura.S1.raw_after`, `measure.M7.cost`, `percentile`, `event.EV2.score`.

**Explainer (`explainer.py`).**

- The LLM receives the plan, the facts table (ids and values), the measure cards and district profiles.
- It returns JSON: `summary`, `strengths[]`, `risks[]`, `consequences[]`, `main_tradeoff`.
- **The text must reference numbers only as `{{fact_id}}` placeholders.** The server replaces the placeholders with values.
- The server then rejects any remaining bare digits in the rendered text, except measure/indicator codes such as M7 or S1.
- Unknown fact ids or bare numbers → retry once with the error message → if it fails again, use the template fallback.
- Every rendered claim is marked `verified: true` in the response.

**Advisor (`advisor.py`).** A tool-using agent loop.

- Tools: `simulate(plan)` and `validate(plan)`, backed by the engine.
- Goal: find a valid plan with a higher score within the same budget.
- Limit: 6 tool calls.
- Return the full trace (each tried plan and its engine score) and the best verified plan.
- The server re-simulates the final plan before returning it.
- Without an API key, fall back to `best_single_swap`.
- The LLM then explains the improvement using fact placeholders only.

The LLM prompt must state explicitly: numbers come only from tools or the facts table.

## 9. API

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/state` | rules, indicators, districts, measures (display fields), events catalog, base score |
| POST | `/api/validate` | `{plan}` → validation result, cost, remaining |
| POST | `/api/simulate` | `{plan}` → simulation preview (no percentile, rank or gap) |
| POST | `/api/submit` | `{team_name, plan}` → simulation + percentile, rank, best score, gap, best single swap; stores to leaderboard |
| POST | `/api/explain` | `{plan}` → verified explanation |
| POST | `/api/advise` | `{plan}` → advisor trace + best verified plan |
| POST | `/api/stress-test` | `{plan, buy_responses}` → stress-test object |
| GET | `/api/leaderboard` | teams with score, percentile, resilience average, one-line strategy summary |
| GET | `/api/health` | `{status, llm_mode: "live" \| "fallback", dataset_hash}` |

Invalid plans → HTTP 422 with `{error_code, error}`.

## 10. Frontend (Streamlit, Russian UI)

1. **Start**: team name.
2. **City**: district cards and a heatmap of the 10 indicators (with real units on hover or in the table), profiles and key issues. Show the base score.
3. **Plan builder**: 5 slots.
   - Each slot: pick a measure (grouped by direction), then a district if the measure is district-type.
   - Show the measure card (description, risks, lag, realized share) when a measure is selected.
   - Show a live budget bar with cost and remaining, updated through `/api/validate`.
   - Show violation messages inline.
   - The submit button is disabled while the plan is invalid.
4. **Results**:
   - Score and change versus base
   - Percentile, rank and gap to best
   - District before/after chart
   - Critical values
   - Verified explanation, with a "✓ проверено симулятором" badge
   - Best single swap
   - "Спросить советника" button that shows the advisor trace step by step
5. **Stress test**: table of 7 events, with an option to buy a response from the remaining budget.
6. **Leaderboard**: all teams, sortable by score or resilience.

## 11. Tests (pytest) — required

- `test_golden.py`: every case in `spec/test_cases.json` passes through **our** engine, with score to 2 decimals and the exact error code. Cases with an `event` key need `events.py`; skip them only until it exists.
- `test_parity.py`: our engine equals `spec/reference_scoring.py` on 10,000 random valid plans (seeded), within 1e-9.
- `test_space.py`: 694,395 valid plans; best 57.24; worst 52.04; the dataset example plan (M7 nura, M8 nura, M10 nura, M12, M5 saryarka) scores 56.54, has rank 566, has 693,829 plans strictly below it (percentile 99.92) and a gap of 0.69.
- `test_rules.py`:
  - over-budget plans are rejected by the API, not just the engine
  - determinism
  - two teams submitting the same plan get the same score
  - different plans give different scores
- `test_no_hardcoding.py`: load a modified copy of the dataset in a temp dir (for example with a 6th district added and one cost changed). The engine must run and reflect the changes.
- `test_events.py`: the official score is unchanged after a stress test; buying a response costing more than the remaining budget → `RESPONSE_OVER_BUDGET`.
- `test_ai.py` (with the LLM mocked): placeholder rendering works; bare numbers are rejected; the fallback works with no key; the advisor never returns an invalid plan or an unverified score.

Before finishing any task, run `pytest -q` and `python spec/reference_scoring.py`. Both must pass.

## 12. README requirements

The README must include:

- Problem and approach
- Architecture diagram
- The scoring formula with reasoning
- Dataset description (synthetic, no personal data)
- One-command launch and local launch
- `.env` setup, noting that the app works without a key
- Main user scenario with screenshots
- A table mapping each jury criterion to its implementation and tests
- How the AI is prevented from inventing numbers
- Limitations and future work

## 13. Working style

- Make one focused change per task, and keep the diffs small.
- Do not add dependencies beyond §4 without saying why.
- Type hints everywhere; engine functions are pure.
- If an instruction here conflicts with a user request, follow the user but point out the conflict. The one exception: never edit `spec/` without explicit confirmation.
