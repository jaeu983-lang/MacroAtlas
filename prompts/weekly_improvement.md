Read `AGENTS.md`, `GUIDELINES.md`, `README.md`, and the existing source/tests before doing anything.

Task: perform a conservative weekly maintenance and improvement pass.

1. Inspect the repository and recent Git history.
2. Run the existing tests first and record the baseline result.
3. Identify at most three concrete, evidence-based improvements. Prioritize defects, missing tests, data integrity, security, and maintainability. Do not invent work.
4. Implement only low-risk changes inside the current repository. Do not add a real data-source connector unless official API documentation and test fixtures are available locally.
5. Add or update deterministic tests. Prefer mocked HTTP responses over live calls.
6. Run the full test suite and `git diff --check`.
7. Do not access secrets, unrelated folders, personal files, or external systems.
8. Do not enable network access, disable sandboxing, commit, merge, deploy, publish, or delete source data.
9. If there is no justified improvement, make no code changes and report that conclusion.
10. Finish with a concise report: findings, files changed, tests and exact outcomes, risks, and manual review steps.

The user must review the branch and diff before any merge.
