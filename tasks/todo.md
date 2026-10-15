# Tasks: Multi-Step Autonomous Web Browsing

- [x] Task 1: Multi-Turn Coordinator Loop & Observation Feedback
  - Acceptance: `MultiAgentCoordinator.run_multi_agent` loops while `proposed_actions` are returned and `rounds < max_rounds`. Tool observations are fed back to `PlannerAdapter`.
  - Verify: Unit test verifying 2-turn and 3-turn fake planner execution terminates cleanly.
  - Files: `app/agents/multi_agent_coordinator.py`, `app/agents/adapters.py`

- [x] Task 2: Search Result Formatting & Auto-Navigation Helpers
  - Acceptance: DOM snapshot formatting highlights search result links clearly so the LLM easily identifies article titles.
  - Verify: Unit test verifying search result elements are tagged and snapshot lists them cleanly.
  - Files: `app/tools/browser.py`

- [x] Task 3: Test Suite & Realtime End-to-End Verification
  - Acceptance: Complete test suite passes with zero regressions. End-to-end multi-turn web search test passes.
  - Verify: `pytest tests/test_multi_turn_autonomy.py -v` and `pytest tests -q`.
  - Files: `tests/test_multi_turn_autonomy.py`
