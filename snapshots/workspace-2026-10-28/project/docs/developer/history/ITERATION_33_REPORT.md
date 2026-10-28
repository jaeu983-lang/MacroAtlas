# Iteration 33 — INSEE codelist metadata

**2026-10-25 / Gate X:** engineering PASS; selected INSEE codelist live sub-gate PASS.
Branch: `codex/iterations-33-34-api-metadata`. User D-103 explicitly authorized
33 then 34, with separate engineering gates, reports and feature commits.

## Actual result and evidence

Officially documented direct BDM request:
`https://bdm.insee.fr/series/sdmx/codelist/FR1/CL_NATURE/1.0`.
**One GET, HTTP 200, zero retries, concurrency one.** Selected agency FR1,
ID CL_NATURE, version 1.0, nonempty distinct code IDs/labels and XML source
contract passed; archive/manifest/hash read-back passed. Stored **10,180 bytes**,
SHA-256 `5df95d6e01eb84877c474b9d8e56fb4165cb72de32738183f40c485c5b8fcbc1`.

- [Live report](../../../reports/iteration_33_api_metadata_3aa7f72656bd4d6c82eca3908d4a8608.json)
- [Synthetic report](../../../reports/iteration_33_api_metadata_5d210b651156412685aaea28d4614ca3.json), HTTP 0
- [Raw entity](../../../data/raw/api/EU-05/9bf782a831334fd785aa7ad3be63f4e4/response.bin), [manifest](../../../data/raw/api/EU-05/9bf782a831334fd785aa7ad3be63f4e4/request.json)
- [Recorded fixture provenance](../../../tests/fixtures/sdmx_metadata/recorded_insee_nature.provenance.json), separate from synthetic `insee-nature.xml`
- [Official route/access/terms audit](../connectors/INSEE_METADATA_RECOVERY.md)

The prior IPC-2015-COICOP DSD request's Iteration 32 HTTP 404 remains failed.
This proves one codelist metadata resource, not that DSD, current dataset catalogue,
observations, broad authentication/coverage, statistical equivalence or workflow.
Census/BLS HTTP 0, Gate U NOT PASSED unchanged. Other sources were not recalled.

## Changes and reasons

- `connectors/sdmx.py`: documented INSEE `get_codelist` method using existing bounded transport and explicit structure XML negotiation.
- `discovery/sdmx_metadata_validation.py`: distinct `insee-nature` selection with iteration=33; strict nonempty/unique code ID and label contract. Existing parser/namespace/source/error checks remain.
- `scripts/verify_api_metadata.py`: report iteration derives from registered selections; mixing numbered budgets is rejected. Defaults stay BEA/e-Stat; old INSEE selection remains historical and explicit.
- `tests/test_sdmx_metadata_checks.py`, synthetic/recorded fixtures: safety/identity/error/oversize/storage regressions include the new selection; specific empty/duplicate/missing code checks and recorded hash/provenance test.
- Registry/test and institution status: INSEE metadata-only PARTIAL for CL_NATURE, with prior DSD failure retained. Plan/decision/AGENTS document the user-directed two-iteration exception.

## Validation and security

- Pre-live full offline: **1,059 passed, 1 skipped, 0 failed, 75.35 seconds**.
- Changed Python Ruff PASS; synthetic runner contract/archive/read-back PASS.
- One Windows symlink limitation skip; repository-local basetemp in approved shell.
- Recorded entity copied after configured credential scan and hash-checked read-back;
  public code metadata only, no personal records selected. Actual keys and `.env`
  unchanged, no key sent, no provider errors printed, no redirects or automatic retries.
- Final recorded/registry/runner regression: **250 passed, 0 failed (5.03 seconds)**;
  changed Python Ruff PASS. Commit preflight scans staged code/docs/fixtures and
  both new run reports/raw/manifest for actual configured credentials; recorded
  Git blob hash must match provenance before commit.

## Remaining work / human decision

The old DSD still needs current official identifier evidence before another
request. No extra INSEE call is made. IMF is the next authorized independent
Iteration 34, beginning only after this engineering/report checkpoint. It must
obtain documented route/auth evidence before an adapter or live request.
Main merge/push/deployment and Iteration 35 are outside authorization.
