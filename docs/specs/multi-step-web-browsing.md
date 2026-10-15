# Spec: Multi-Step Autonomous Web Browsing Loop

## Objective
Enable JASPER's `MultiAgentCoordinator` to run an autonomous ReAct loop (Reason → Act → Observe → Reason → Act) across multiple consecutive turns. 

Specifically, for web research:
1. **Turn 1 (Search):** Navigate to search engine and enter the user query.
2. **Turn 2 (Observe & Select):** Observe search result links, choose the top relevant result, and click/open it.
3. **Turn 3 (Read & Extract):** Read the target webpage content.
4. **Turn 4 (Synthesize):** Deliver the final answer to the user and terminate the loop.

## Tech Stack
- Language: Python 3.12 (Virtualenv: `.\.venv`)
- Engine: Playwright Chromium (Headed realtime mode)
- LLM Provider: Local Ollama (`qwen3:14b` via `http://127.0.0.1:11434`)
- UI / Async: PySide6 QThread + Python `asyncio`

## Commands
- **Unit & Integration Test:** `.\.venv\Scripts\python.exe -m pytest tests/test_multi_turn_autonomy.py -v`
- **Full Test Suite:** `.\.venv\Scripts\python.exe -m pytest tests -q`
- **Run Desktop App:** `.\.venv\Scripts\python.exe -m app.desktop`

## Project Structure
- `app/agents/multi_agent_coordinator.py`: Core multi-turn execution loop and termination gate.
- `app/agents/coordinator.py`: Coordinator budget tracking and round charging.
- `app/agents/adapters.py`: Formats multi-turn tool observations into Planner/Executor message context.
- `app/tools/browser.py`: Realtime headed Chromium interaction (auto-routing, navigation, reading).
- `tests/test_multi_turn_autonomy.py`: Comprehensive test suite for multi-turn cycles and budget guards.

## Multi-Turn Contract & State Machine

```
[User Request]
       │
       ▼
 ┌───────────────┐
 │ 1. PLANNER    │◄───────────────────────────┐
 └───────┬───────┘                            │
         │ (Proposed Actions)                 │
         ▼                                    │ (Tool Observations)
 ┌───────────────┐                            │
 │ 2. EXECUTOR   │                            │
 └───────┬───────┘                            │
         │ (Validated Actions)                │
         ▼                                    │
 ┌───────────────┐                            │
 │ 3. TOOL RUN   │ ──► [Approval Gate if Risk.WRITE]
 └───────┬───────┘                            │
         │ (Result / DOM Snapshot)            │
         ▼                                    │
   [Turn Complete?]                           │
    ├── NO: proposed_actions > 0 ─────────────┘
    │       and rounds < max_rounds (4)
    │
    └── YES: proposed_actions == 0 OR rounds == max_rounds
            │
            ▼
   [Synthesize & Output Final Answer to User]
```

## Boundaries & Safety
- **Always:** Enforce `max_rounds = 4` hard limit to guarantee zero runaway or infinite loops.
- **Always:** Route state-changing actions (`Risk.WRITE`) through `ApprovalGate` and the PySide6 `ApprovalDialog`.
- **Always:** Clean up browser sessions on task cancellation or window close.
- **Never:** Drop or ignore tool errors; surface them into the next turn so the Planner can self-correct.

## Success Criteria
- [ ] Planner can inspect previous turn observations (e.g. search results) and decide the next action.
- [ ] Multi-turn loop terminates naturally when the Planner outputs text with 0 proposed actions.
- [ ] If max rounds is reached, coordinator synthesizes all gathered observations into a coherent answer rather than crashing.
- [ ] 100% test pass rate across the full repository test suite.
