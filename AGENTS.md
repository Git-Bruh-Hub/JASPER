# AGENTS.md — Development Rules for AI Agents Working on JASPER

> **Target Audience:** All AI agents, assistants, pair programmers, and autonomous coding tools working in this repository.  
> **Mandatory Status:** These instructions are binding rules. Follow them strictly.

---

## 1. Project Brain First

Before proposing architecture, writing code, running tests, or planning tasks:
1. **Read the Project Brain:**
   - [`PROJECT_VISION.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/PROJECT_VISION.md): Core mission, long-term destination, and safety invariants.
   - [`PROJECT_STATE.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/PROJECT_STATE.md): Ground-truth verified state, tests, and uncommitted artifacts.
   - [`ARCHITECTURE.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/ARCHITECTURE.md): Implemented request flows, contracts, and security boundaries.
   - [`ROADMAP.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/ROADMAP.md): Ordered milestones, acceptance criteria, and dependencies.
   - [`DECISIONS.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/DECISIONS.md): Architectural decisions (ADRs) and trade-offs.
   - [`JASPER.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/JASPER.md): Master handover and historical context.
2. **Do Not Hallucinate Implemented Capabilities:**
   - Check the code before asserting that a feature exists.
   - Separate verified code from roadmap goals.

---

## 2. Git Safety & Preservation of Work

### Mandatory Invariants:
1. **Never Run Destructive Git Commands:**
   - **PROHIBITED:** `git reset --hard`, `git clean -fd`, `git restore .`, `git checkout -- .`, or any command that discards local work.
   - If an unexpected file or diff exists, inspect and classify it. Never discard it simply because it is uncommitted.
2. **Never Use `git add .`:**
   - Always stage explicit, named files: `git add <exact-file-path>`.
3. **Never Commit or Push Without Explicit Approval:**
   - Always present the exact proposed commit message and list of changed files to the user and wait for their confirmation.
4. **Preserve Untracked Artifacts:**
   - You must preserve:
     - `diff.patch`
     - `docs/` (`docs/planning/`)
     - `graphify-out/`
     - `security-recovery-backup/`
     - Any existing user recovery, test, or patch files.
5. **Inspect Before Acting:**
   - Begin every session with read-only Git inspection (`git status -s`, `git branch -vv`, `git log -n 5 --oneline`).

---

## 3. Python Environment & Command Invariant

All Python commands (running tests, scripts, modules, or checking dependencies) **MUST** use the local project virtual environment explicitly:

```powershell
.\.venv\Scripts\python.exe
```

**Never use system/global `python`, `pytest`, or `pip`:**
- Correct: `.\.venv\Scripts\python.exe -m pytest <path-to-test>`
- Correct: `.\.venv\Scripts\python.exe -m pip list`
- Correct: `.\.venv\Scripts\python.exe -m app.desktop`
- Incorrect: `pytest`
- Incorrect: `python -m pytest`

---

## 4. Evidence-Based Reporting & Labels

When documenting or reporting on the repository, strictly apply these evidence labels:
- **[VERIFIED]:** Directly proven by reading current source code, inspecting Git history, or reproducing command output in this session.
- **[INFERRED]:** A reasoned deduction or likely interpretation that is not directly proven by an artifact.
- **[PLANNED]:** An intended design or roadmap capability that is not yet implemented or verified in code.

Never describe a planned capability as implemented. Never describe the entire test suite as passing unless every test in the suite was actually executed and passed.

---

## 5. Development Workflow (Step-by-Step)

When implementing changes for an approved milestone:
1. **Implement Only the Approved Milestone:** Do not add speculative code for future milestones.
2. **Incremental Delivery:** Deliver thin, testable slices.
3. **Run Relevant Regression Tests:** Use `.\.venv\Scripts\python.exe -m pytest <tests>` to prove correctness.
4. **Review Working-Tree Diffs:** Inspect `git diff` to ensure no unintended files or whitespace churn were introduced.
5. **Preserve Comments & Docstrings:** Do not delete existing explanatory comments or docstrings unrelated to your changes.
6. **Report Evidence & Recommend Next Step:**
   - Summarize files changed.
   - Report test results with exact counts and commands used.
   - Propose the next logical roadmap milestone, explain why it matters, list alternatives, and **STOP**.
   - Wait for user review and approval before proceeding.

---

## 6. Antigravity & Tooling Integration

- **Knowledge Graph Rules (`.agents/rules/graphify.md`):**
  - Use `graphify-out/` knowledge graph for codebase navigation when applicable.
  - **Exception / Preservation Rule:** Defer running `graphify update .` if doing so would overwrite or regenerate modified untracked user graph artifacts (`graphify-out/`) unless explicitly requested by the user. Preserving user artifacts takes precedence over automatic graph updates.
