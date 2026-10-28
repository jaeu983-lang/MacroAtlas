# Evaluation scaffolds and evidence-backed cases

This documentation covers three separate inputs: the original JSON-per-split
scaffold in `evaluation/sets/`, the initial evidence-backed JSONL v1 corpus in
`tests/fixtures/evaluation/v1/`, and the GPT-reviewed v2 corpus in
`tests/fixtures/evaluation/v2/`. None is an automatic learner.
`macro-feedback` keeps an append-only feedback revision log; accepted feedback
does not enter an evaluation corpus unless a reviewer creates, verifies, and
privacy-clears a case explicitly. Periodic AI categorization of prior revisions
is not implemented. When added, classifications must be versioned derived data
with exact one-to-one source revision coverage; the source log stays unchanged.
Product requirements and current implementation order are in [PROJECT_PLAN.md](../PROJECT_PLAN.md) §7 and §11. This file defines the case schema only.

## Current state

The original split-set scaffold and v1/v2 JSONL corpora are separate contracts.
The legacy scaffold has six synthetic cases. The initial v1 corpus remains at
9/36 and BLOCKED as a historical version. The v2 corpus has 36/36 cases, 12
per split and three per case type per split, and validates READY.

The original 27 assistant-simulated draft files remain unchanged with their
generation-time `independent_review_pending` metadata. A separate v2 review
ledger records GPT-6's case-by-case result against the exact draft hash,
accepted case version, evidence hashes, privacy basis, and corrections. Twenty
six were approved as written; one GDP total/per-capita case was corrected and
approved as version 2. The ledger identifies an AI reviewer and does not claim
human review or human-observed usage.

The v2 validator verifies structure, hashes, case-to-review links, evidence
references, and split leakage. READY means the case corpus is complete and
internally verified; it does not run a search engine or promote a search rule.
`macro-eval search-baseline` and `search-compare` run development cases offline;
`search-validation` compares the same baseline and candidate on validation.
Those ranker commands do not evaluate holdout. `macro-gate-c qualify` runs development and
validation, sends every proposal without confirmation to the real collection
plan builder, and records whether the type boundary blocks it before task
creation. The prohibition trace covers confirmation/selection, unknown-field
disclosure, and whether raw/export or merge/fill actions remain unreachable before
plan creation. A caveated official label that explicitly says its full definition
is missing is recorded as a disclosure, not an inferred full definition. This
trace does not exercise a raw writer or exporter internally. It measures the local
search stage repeatedly by case type and records p50/p95, throughput, equal sample
counts, and zero external calls/cost. It does not run a source API, external model,
task, raw write, or export.

Only after the qualification report and candidate manifest are committed may
`macro-gate-c initialize-holdout` create a one-use lock. The lock must also be
committed before `macro-gate-c holdout` is run. That command checks the frozen
case, catalog, policy, code, and timing-budget hashes; it consumes the lock
before evaluation so a failure or interruption cannot silently be rerun. The
holdout is a separate public-repository split, not secret data. Validation
cases used during candidate refinement are not blind evidence. A passing search
Gate still does not promote the candidate or prove general statistical
equivalence; those claims require separate review and Gate D.

The fixed v2 run completed with Gate C `PASS` on 2026-10-28. Its one-use lock
is consumed; the aggregate result is in
[`gate_c_holdout_result.json`](../evaluation/results/gate_c_holdout_result.json).
Do not rerun this split. The candidate remains evaluation-only and has not been
promoted. A future tuning cycle needs a new versioned corpus/holdout split.

Reports include ranking, expected state, missing relevant candidates,
unrelated abstention, forbidden candidate returns, false-exact candidates, and
structural field/status checks. The CLI does not send queries to an AI model: it
runs the local deterministic ranker on stored case questions. GPT-6 was used
earlier to review this fixed corpus, not as an automated judge for each
evaluation run.
## Legacy scaffold record

`macro-eval feedback-draft` is the opt-in bridge for an accepted current
`user_instruction`. It requires the selected feedback ID/revision, a sanitized
question, a reviewer ID, and an explicit `--privacy-cleared` attestation. It
writes a no-overwrite local seed under `data/feedback_case_drafts/`; `.gitignore`
keeps this user-derived output out of version control. The seed omits original
feedback text, task ID, scope, and source evidence, targets development only,
and remains incomplete until its expected result, official evidence, forbidden
actions, Excel policy, and case review are authored. It never changes a split
set or v1/v2 corpus. No real user feedback has been bridged yet.

Each case has a stable `case_id`, integer `case_version`, assigned split,
canonical question and paraphrase variants, expected response state and source
entity/field, required evidence, forbidden actions, and an explicit Excel
expectation. It also records reviewed provenance, feedback reference when
applicable, reviewer/time, and privacy clearance. The validator rejects
unreviewed or uncleared cases, unknown fields, duplicate IDs, repeated exact
questions across splits, and contrast groups split across sets. It reports
provenance counts for each split. `reviewed_feedback_split_coverage` only
summarizes declared feedback-origin labels; synthetic and official-reference
cases do not count as reviewed-feedback cases, and the validator does not
verify feedback IDs against the feedback log.

Illustrative record shape (documentation example only; it is not counted as an
evaluation case):

```json
{
  "schema_version": 1,
  "case_id": "example-do-not-run",
  "case_version": 1,
  "split": "development",
  "review": {
    "status": "reviewed",
    "reviewer": "reviewer-id",
    "reviewed_at": "2026-10-27T00:00:00+00:00",
    "privacy_cleared": true
  },
  "provenance": {
    "origin": "synthetic",
    "feedback_id": null,
    "evidence": []
  },
  "contrast_group": null,
  "question": {
    "canonical": "Example query",
    "variants": ["Example paraphrase"]
  },
  "expected": {"state": "NEEDS_REVIEW", "entities": []},
  "required_evidence": ["source_url", "definition"],
  "forbidden_actions": ["guess_identifier", "interpolate_missing_values"],
  "excel_expectation": {
    "policy": "not_applicable",
    "missing_value": "not_applicable",
    "overlap_conflict": "not_applicable",
    "interpolate": false,
    "forward_fill": false
  }
}
```

Assign semantically similar questions with different expected answers to the
same `contrast_group`; the validator cannot infer semantic similarity by itself.
All members of a contrast group stay in one split. Cases derived from feedback
must use sanitized question text and retain only a feedback identifier in the
case provenance, not the private feedback body.

Excel expectation fields are required even before an Excel exporter exists.
`interpolate` and `forward_fill` must remain false. Use `blank` for missing
values when an Excel output is applicable; overlapping incompatible series
must be kept separate or sent for review.

## Evidence-backed `EvaluationCase` v1 record

The JSONL corpus uses the richer immutable contract in
`src/macro_data_platform/evaluation/case_contracts.py`. Each record fixes its
case family and split, type, `DataRequest` snapshot, query variants, expected
state, relevant/forbidden candidate IDs, candidate match statuses, expected
field states, evidence references, prohibited actions, and Excel policy.
Evidence paths are repository-relative and hash checked; official references
must be clean HTTPS URIs without credential-bearing query data. Unknown or
conflicting expected fields require supporting evidence and a review-required
candidate status. Assistant authorship remains simulated provenance and cannot be marked human-observed. Review decisions live in the separate ledger and do not rewrite draft authorship. The current v2 ledger explicitly marks GPT-6 as an AI reviewer.

## AI-simulated development evidence

By user decision, AI-authored and AI-reviewed simulated user cases may contribute to Gate evaluation
when their provenance and split are recorded. `python -m macro_data_platform.evaluation.synthetic_gate_evidence`
compares the two reviewed synthetic examples against the same fixed catalog and labels them `ai_simulated`,
`human_observed=false`. These already-observed examples overlap the existing development material; they are
not added to the v2 corpus quota and cannot be treated as independent validation or holdout. The comparison
does not measure downstream actions, user observation, holdout, or promotion and cannot pass Gate C on its own.
The reviewed expectations state the reviewer, UTC time and `same_assistant` provenance; reviewer identity is
recorded as supplied rather than independently authenticated.
For other reviewed AI cases, supply `--cases` and `--expectations` JSON with the same schema. The tool is
development-only and does not independently detect semantic split leakage; review case families before using them.

## Not implemented by this step

The validator does not authenticate source evidence or approve a rule. Development
ranking scores on the v2 set are offline fixture measurements, not evidence of
production accuracy or analyst usability. The one-time holdout command measures
the fixed ranker candidate only; it does not prove statistical equivalence or
exercise source API, raw-write, export, or human workflow. The `macro-promotion`
CLI verifies the frozen evidence hashes and records explicit accept/hold/reject
and rollback events. It does not authenticate identities or change default policy;
the current ledger has no human decision, so the candidate remains unpromoted.
