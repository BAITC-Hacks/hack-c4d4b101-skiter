# How to build «Аким на 5 часов» with Codex

This guide is for your team. `AGENTS.md` is for Codex: it reads that file automatically at the start of every session, so you don't need to paste the rules into prompts. This guide covers how to set up the repo, which prompts to give Codex and in what order, and how to check its work.

## 1. What each file is for

| File | Who uses it | Purpose |
| --- | --- | --- |
| `AGENTS.md` | Codex | Project rules, architecture, API, tests. Codex reads it automatically. |
| `spec/city_dataset.json` | The app | All data the app loads. Nothing about the city is written into code. |
| `spec/test_cases.json` | The tests | Answer key: 19 plans with their correct results. |
| `spec/reference_scoring.py` | You and Codex | Working reference implementation. The app must match it exactly. |
| `spec/Датасет_районов_расширенный.docx` | Jury and humans | Readable spec. Codex doesn't need it. |
| `CODEX_GUIDE.md` (this file) | Your team | How to work with Codex. You can keep it out of the repo. |

## 2. One-time setup

1. Create a Git repository, for example `akim-5h`.
2. Put the files in place:
   ```
   akim-5h/
     AGENTS.md
     spec/
       city_dataset.json
       test_cases.json
       reference_scoring.py
       Датасет_районов_расширенный.docx
   ```
3. Check that the reference works:
   ```bash
   python spec/reference_scoring.py      # must end with: 19/19 passed
   ```
4. Commit: `git add . && git commit -m "spec + agent instructions"`.
5. Start Codex from the repository root, so it picks up `AGENTS.md`. You can use the CLI (`codex` in the terminal), the IDE extension, or Codex cloud connected to your GitHub repo. Any of these works. What matters is that the repo root contains `AGENTS.md`.
6. Optionally ask Codex first: *"Summarize the rules you must follow in this repo."* If it mentions the read-only `spec/` folder, the LLM-never-computes rule and server-side budget checks, it has loaded the instructions.

## 3. How to work with Codex (important)

- **One phase per prompt.** Don't ask for the whole app at once. Small tasks give better code and diffs you can actually review.
- **Commit after every phase that passes.** If Codex breaks something later, you can roll back.
- **Always run the checks yourself** after a phase: `pytest -q` and `python spec/reference_scoring.py`.
- **Watch for three red flags in diffs:**
  1. Any change inside `spec/` → reject it.
  2. Numbers like `52.56`, `"nura"` or `"M7"` inside application logic (not tests) → that's hard-coding, so ask Codex to read them from the dataset.
  3. A test whose expected value was changed so it passes → reject it. The code is wrong, not the answer key.
- **If Codex says a golden test is wrong,** run `python spec/reference_scoring.py`. If the reference passes, the test is right.

## 4. Build order and prompts

Copy each prompt into Codex. The "Done when" line is what you check before committing.

### Phase 1 — Project skeleton
> Create the repository structure from AGENTS.md §5: backend package, frontend folder, scripts folder, requirements files, `.env.example`, `.gitignore`, and a minimal FastAPI app with `/api/health`. Don't implement the engine yet.

**Done when:** `uvicorn backend.app.main:app` starts and `/api/health` responds.

### Phase 2 — Engine and golden tests (the most important phase)
> Implement `engine/dataset.py`, `engine/validator.py` and `engine/simulator.py` by porting `spec/reference_scoring.py` into clean, typed, dataset-driven code (AGENTS.md §6–7). Then write `test_golden.py` (skip cases that have an `event` key until Phase 9, marked with `pytest.mark.skip`), `test_parity.py`, `test_rules.py` (engine-level parts) and `test_no_hardcoding.py` as described in §11. Don't touch `spec/`.

**Done when:** all tests pass, including the 15 non-event golden cases and the 10,000-plan parity check.

### Phase 3 — Natural units
> Implement `engine/units.py` per AGENTS.md §7 and include before/after real-unit values in the simulation result. Add tests: Nura S1 after the dataset example plan must be 74% of the norm (from 69%).

**Done when:** tests pass and the simulation output shows real-unit values.

### Phase 4 — API
> Implement the endpoints from AGENTS.md §9, except `/api/explain`, `/api/advise` and `/api/stress-test`, which come in later phases. Invalid plans return 422 with an error code. Add API tests showing an over-budget plan is rejected by the server.

**Done when:** `/api/state`, `/api/validate`, `/api/simulate` and `/api/submit` work (submit without percentile for now), and tests pass.

### Phase 5 — Streamlit UI (must-have demo)
> Build `frontend/app.py` per AGENTS.md §10, sections 1–4 and 6. Skip the explanation, advisor and stress test for now. Use a live budget bar via `/api/validate` and inline violation messages. Disable submit while the plan is invalid. All UI text in Russian.

**Done when:** you can play a full round in the browser and the budget can't be exceeded.

At this point you have a working MVP that meets every must-have except the AI explanation. Commit and tag it `mvp`.

### Phase 6 — Solution space (differentiator 1)
> Implement `scripts/precompute_space.py` and `engine/space.py` per AGENTS.md §7: cache sorted scores keyed by the dataset hash, then add percentile, rank, best_score and best_single_swap. Return these from `/api/submit` only. Write `test_space.py` with the exact values from §11.

**Done when:** tests confirm 694,395 valid plans, rank 566 for the example plan, and startup loads the cache in about a second.

### Phase 7 — Verified explainer (differentiator 2)
> Implement `ai/llm.py`, `ai/facts.py` and `ai/explainer.py` per AGENTS.md §8, using fact placeholders, server-side rendering, bare-number rejection, one retry, and the template fallback when no API key is set. Add `/api/explain` and show the explanation in the UI with the verified badge. Write `test_ai.py` with the LLM mocked.

**Done when:** the explanation works both with and without an API key, and the tests show that invented numbers are rejected.

### Phase 8 — Advisor agent (differentiator 2)
> Implement `ai/advisor.py` per AGENTS.md §8: a tool-calling loop with simulate and validate, at most 6 tool calls, a full trace, re-verification of the final plan, and `best_single_swap` as the fallback. Add `/api/advise` and a UI button that shows the trace step by step.

**Done when:** the advisor never returns an invalid plan, every score in the trace comes from the engine, and it works without a key.

### Phase 9 — Stress test (differentiator 4)
> Implement `engine/events.py` and `/api/stress-test` per AGENTS.md §7 and §9. Add the stress-test panel to the results page, with the option to buy responses from the remaining budget. Write `test_events.py`. The official score must never change.

**Done when:** the event golden cases (TC16–TC19) are un-skipped and pass, and the official score is unaffected.

### Phase 10 — Leaderboard
> Implement SQLite storage and `/api/leaderboard` with score, percentile, resilience average and a one-line strategy summary built from the engine result, not the LLM. Add the leaderboard page.

### Phase 11 — Packaging and README
> Add `docker-compose.yml` so `docker compose up` runs the backend and frontend. Write README.md per AGENTS.md §12, including the jury-criteria table. Leave clear placeholders for screenshots. Verify that the documented commands work from a fresh clone.

**Done when:** a teammate clones the repo on another machine, follows the README only, and gets a working app.

## 5. If you're short on time

Must reach: Phases 1–5 plus Phase 7 (fallback mode alone counts as the AI explanation for must-have purposes), then Phase 11.
Differentiator priority: Phase 6 → Phase 8 → Phase 9 → Phase 10.

To split work across people, Phases 6, 7 and 9 can run in parallel once Phase 4 is merged, because they touch different files.

## 6. Final checklist before submission

- [ ] `python spec/reference_scoring.py` → 19/19 passed
- [ ] `pytest -q` → all green
- [ ] `git diff <first-commit> -- spec/` is empty (spec untouched)
- [ ] App runs with an empty `LLM_API_KEY` (fallback mode)
- [ ] Over-budget plan is rejected by the API directly (test with curl, not only the UI)
- [ ] Two teams with different plans get different scores; the same plan gives the same score
- [ ] README works on a fresh clone; screenshots added
- [ ] Demo rehearsed: plan → percentile → advisor trace → verified explanation → blizzard stress test → leaderboard
