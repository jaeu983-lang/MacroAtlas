# Evaluation scaffolds and evidence-backed cases

This documentation covers three separate inputs: the original JSON-per-split
scaffold in `evaluation/sets/`, the initial evidence-backed JSONL v1 corpus in
`tests/fixtures/evaluation/v1/`, and the GPT-reviewed v2 corpus in
`tests/fixtures/evaluation/v2/`. None is an automatic learner.
`macro-feedback` keeps the append-only runtime feedback log; accepted feedback
does not enter an evaluation corpus unless a reviewer creates, verifies, and
privacy-clears a case explicitly.
Product requirements are in [PROJECT_PLAN.md](../PROJECT_PLAN.md); the current implementation order is in [PRODUCT_EVALUATION_ENGINE_PLAN.md](PRODUCT_EVALUATION_ENGINE_PLAN.md).

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
internally verified; it does not run a search engine, calculate ranking
accuracy, or promote a search rule. The ranking evaluator and rule-promotion
workflow are not implemented.
## Legacy scaffold record

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

## Not implemented by this step

The validator does not authenticate source evidence, run an engine, calculate
answer/ranking accuracy, compare baseline and candidate rules, calculate
false-confirmation rates, or approve a rule. The legacy synthetic cases exercise
structure only; neither the v1 nor v2 cases have been scored by an engine. The
v2 set is an AI-reviewed, source-backed regression fixture, not evidence of
production ranking accuracy or analyst usability. Rule promotion and rollback
remain explicit decisions with no automatic feedback-to-code path.
