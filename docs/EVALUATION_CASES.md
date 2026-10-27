# Evaluation scaffolds and evidence-backed cases

This documentation covers two separate inputs: the original JSON-per-split
scaffold in `evaluation/sets/` and the evidence-backed JSONL v1 corpus in
`tests/fixtures/evaluation/v1/`. Neither is an automatic learner.
`macro-feedback` keeps the append-only runtime feedback log; accepted feedback
does not enter an evaluation corpus unless a reviewer creates, verifies, and
privacy-clears a case explicitly.
The complete feedback→evaluation→promotion contract and priority order are in
[`PROJECT_PLAN.md`](../PROJECT_PLAN.md), §7 and §11.

## Current state

The original split-set scaffold has six synthetic contract cases, two per
split. It covers the fixed World Bank and BOJ paths, a BLS CPI
contrast between a qualified and ambiguous request, incompatible frequencies
in Excel, and unknown-frequency freshness. They are author-generated fixtures,
not user feedback or evidence that live providers returned the expected data.
The reviewer field records the synthetic author's self-review; it is not an
independent human review.

Its validation and holdout file bytes and versions are pinned in
`evaluation/sets/frozen.json`. A change to either frozen set must include a
deliberate, reviewed lock update in the same PR. The hash detects unreviewed
drift; it does not make the public holdout secret or prevent an approved
baseline change. The validator reports structural `READY` separately from
`reviewed_feedback_split_coverage` (`none`, `partial`, or `complete`). Coverage
is based only on declared provenance labels; the validator does not
authenticate feedback IDs against the SQLite feedback log. Neither status
scores engine behavior. These six synthetic cases are scaffolding only and do
not satisfy the user-evidence or generalization gate.

This scaffold is not the current gold evaluation corpus and does not evaluate
engine behavior. The v1 evidence-backed corpus is the versioned JSONL source
for the planned search-evaluation gate. Its current manifest contains 9 of 36
target cases across the three splits and is explicitly `blocked`. One fixed
World Bank candidate is retained with local official evidence hashes; the
manifest does not claim broader catalog coverage. A separate 27-case pool is
marked `independent_review_pending`. Those assistant-simulated drafts remain
outside the fixed catalog and corpus; hash and text-template checks do not
replace independent semantic review. No engine evaluator or rule promotion is
implemented by these files.

Validate the original scaffold from the repository root:

```text
python -m macro_data_platform.evaluation.cli validate
```

After installing the project, the equivalent command is:

```text
macro-eval validate
```

Validate the evidence-backed v1 corpus and its evidence file hashes with:

```text
python -m macro_data_platform.evaluation.cli validate-corpus
```

This command returns exit code 2 while the corpus gate is blocked or invalid.
It reports verified inputs and gate blockers; it never promotes drafts or runs
the search engine.

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
candidate status. Agent/assistant authorship is preserved as simulated and
cannot be marked human-observed.

## Not implemented by this step

The validator does not authenticate source evidence, run an engine, calculate
answer/ranking accuracy, compare baseline and candidate rules, calculate
false-confirmation rates, or approve a rule. The current synthetic cases only
exercise corpus structure. A representative evaluation still needs
independently reviewed cases and verified feedback/source references, plus a
shared, versioned outcome record from the product engines. Rule promotion and
rollback remain explicit human decisions with no automatic feedback-to-code
path.
