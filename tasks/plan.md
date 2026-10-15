# Implementation Plan: Multi-Step Autonomous Web Browsing Loop

## User Review Required
> [!IMPORTANT]
> The multi-turn loop enables the Planner to run up to 4 consecutive reasoning rounds. Each round executes proposed actions and feeds observations back to the Planner until the Planner finishes with a text answer.

---

## Proposed Slices

### Slice 1: Multi-Turn Coordinator Loop & Observation Feedback
- **Files:** `app/agents/multi_agent_coordinator.py`, `app/agents/adapters.py`
- **Goal:** Allow `run_multi_agent` to loop across turns (up to `max_rounds=4`). When tools execute, their outputs and DOM snapshots are appended to `task.history` so the Planner sees what happened in the previous turn and decides the next step. Loop stops when Planner returns 0 proposed actions or reaches max rounds.

### Slice 2: Browser Search Result Extraction & Safe Navigation
- **Files:** `app/tools/browser.py`
- **Goal:** Add helper `browser_search(query: str, engine: str = "duckduckgo")` or ensure `browser_navigate` + `browser_type` leaves page on search results with clean numbered result links (`[1] Link: Title`, `[2] Link: Title`).

### Slice 3: Integration Tests & Desktop Verification
- **Files:** `tests/test_multi_turn_autonomy.py`
- **Goal:** Write unit tests for multi-turn loops, testing:
  1. A 3-turn plan (Navigate -> Observe -> Click -> Answer).
  2. Bounded budget termination when max rounds is reached.
  3. Error recovery if a page fails to load.
  4. Run full test suite to guarantee 481+ passing tests.
