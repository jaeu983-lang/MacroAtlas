# Agent Operating Rules

## Project plan precedence
- Read `PROJECT_PLAN.md`, the matching iteration in `docs/developer/IMPLEMENTATION_PLAN.md`, and relevant institution/scenario documentation before new implementation work.
- Treat `PROJECT_PLAN.md` as the product scope and acceptance standard; apply stricter security and data-integrity guidance where different.
- Implement exactly one numbered High iteration per task. Never advance past a failed gate.
- User-directed task exception (2026-10-25, D-103): execute Iterations 33 then 34 sequentially, completing each engineering gate/report before the next. Iteration 33 is INSEE bounded metadata recovery; Iteration 34 is IMF official route/auth readiness and metadata adapter only if documented. Source live failures remain independent; shared engineering/safety failures stop progression. Keep Census/BLS deferred, Gate U NOT PASSED, and no main merge/push/deployment. This exception authorizes no iteration beyond 34.
- User-directed scope change (2026-10-25, D-101): Census and BLS are deferred from the active API rollout until the user resumes them. Gate U remains NOT PASSED; do not retry those sources or reinterpret its original results as success. The user authorized concentrating on other institution APIs, so independent source gates may proceed without Gate U. Iteration 31 completed BEA/e-Stat bounded metadata validation and archive/read-back only; see its report. Future tasks retain the one-iteration rule and select their own numbered scope; no merge or publication is authorized by this exception.
- Completed user-directed exception (2026-10-25, D-057): The one combined iteration 07 -> 08 task completed sequentially, with iteration 07 checks/report finished before iteration 08 began. See docs/developer/history/ITERATION_07_REPORT.md and docs/developer/history/ITERATION_08_REPORT.md for fixture/live scope and results. The exception is consumed; the default one-iteration-per-task rule applies to future work. It grants no commit or merge authorization.
- Completed user-directed exception (2026-10-25, D-062): The user explicitly requested completion through iteration 12. Iterations 09–12 completed sequentially, with Gate C and Gate D reports. This exception is consumed; iteration 13 was not started. It grants no checkpoint, commit, or merge authorization. Future tasks return to the one-iteration-per-task rule.
- Completed user-directed exception (2026-10-25, D-072): The user explicitly requested iterations 13 and 14. They completed sequentially through Gate E; see `docs/developer/history/ITERATION_13_REPORT.md` and `docs/developer/history/ITERATION_14_REPORT.md`. The task-local exception is consumed; future tasks return to one iteration per task. It grants no commit, merge, publish, stage, or checkpoint authorization.
- Distinguish official-docs research, fixture tests, and live API/ingestion evidence.
- Record unresolved design decisions in `docs/developer/history/DECISION_LOG.md`.

## Mission
Build a reliable international-finance data discovery and ingestion platform for public statistical sources.

## Before every task
1. Read `GUIDELINES.md` and this file.
2. Inspect repository status and relevant tests before changing files.
3. Identify the smallest useful change and state assumptions.
4. Never claim that an API endpoint, metadata field, or test result was verified unless it actually was.

## Architecture boundaries
- `discovery/` discovers datasets, series, dataflows, metadata, and source documentation.
- `metadata/` normalizes metadata while preserving the original source representation.
- `mapping/` links source concepts to common concepts and records confidence/reasons.
- `connectors/` contains source-specific API adapters.
- `ingestion/` downloads observations and validates them.
- `analysis/` uses stored data; it must not silently change source observations.
- Keep discovery and ingestion independently testable.
- Prefer adding a source adapter over adding source-specific conditionals throughout the core.

## Data integrity
- Preserve source agency, dataset/series identifiers, retrieval timestamp, source URL, units, frequency, dimensions, and revision/vintage information when available.
- Do not treat missing values as zero.
- Do not infer equivalence from matching labels alone.
- Do not overwrite raw responses silently.
- Respect API terms, rate limits, attribution, and licensing.

## Automation and safety
- Work only within the repository workspace.
- Do not disable sandboxing or bypass approval controls.
- Do not access unrelated folders, browser profiles, credentials, or personal files.
- Never print secrets or place API keys in source files, tests, prompts, or logs.
- Do not make destructive changes, deploy, publish, or merge to the main branch.
- Do not run network-dependent actions unless network access has been explicitly configured and the task requires it.
- Keep automatic changes on a separate Git branch. Human review is required before merging.

## Testing
- Add or update tests for every behavior change.
- Run the full local test suite when practical.
- If a test cannot run, state exactly why; do not mark it as passed.
- Do not weaken or delete tests merely to make a run pass.
- Use deterministic tests and mocked HTTP responses by default.

## Completion report
Summarize:
1. Files changed
2. Reason for each material change
3. Tests run and exact outcomes
4. Known limitations
5. Security/data-integrity implications
6. Whether a human decision is needed
