# Iteration 34 — IMF public CPI dataflow metadata

**2026-10-25 / Engineering Gate Y PASS; selected IMF metadata live sub-gate PASS.**
Branch: `codex/iterations-33-34-api-metadata`. Iteration 33's Gate X, report and
commit `978d9fc` completed before Iteration 34 implementation began.

## Official evidence and actual result

The public [IMF API page](https://data.imf.org/en/Resource-Pages/IMF-API) links
JavaScript-rendered support pages. The MATLAB guide explicitly supplies public
root `https://api.imf.org/external/sdmx/2.1`; the R guide supplies `IMF.STA,CPI`
and public-user access distinct from elevated staff/partner authentication.
Together with the SDMX 2.1 structural query contract this documents the bounded
selection. Swagger redirected to sign-in and was not used to infer API-key
requirements. No login, token, account creation or third-party library install
was performed. [Exact links, terms and route derivation](../connectors/IMF.md).

Request: `https://api.imf.org/external/sdmx/2.1/dataflow/IMF.STA/CPI/latest`.
**One public GET, HTTP 200, zero retries, concurrency one.** It returned the
selected CPI Dataflow, agency IMF.STA, actual version **5.0.0**. Source identity,
XML 2.1 namespace/root, response ID, resource identity/name and DSD reference
passed, as did file/manifest/hash read-back. **3,234 bytes** stored;
SHA-256 `21819c7befea5776e3786dd66f6c6fc1eca6b3479ba893fb95fd435392da2681`.

The response references a DSD not downloaded in this task. The validator keeps
`unresolved_dsd:CPI` explicit. This is one metadata sub-gate, not observations,
full CPI coverage, comparability, private authentication or general workflow.
The official maintenance notice was observed; no retry/fallback was needed.

## Files and reproducible evidence

- [Live report](../../../reports/iteration_34_api_metadata_27f467392f2d4bee99b070b5f98d0f8a.json)
- [Synthetic report](../../../reports/iteration_34_api_metadata_be770815b0e048b2b71601ad721d425e.json), HTTP 0
- [Raw entity](../../../data/raw/api/INT-01/e36c3094145c4922a2c8b60b105d684a/response.bin), [manifest](../../../data/raw/api/INT-01/e36c3094145c4922a2c8b60b105d684a/request.json)
- [Recorded fixture provenance](../../../tests/fixtures/sdmx_metadata/recorded_imf_cpi.provenance.json), records URL, UTC, content type, representation, validation and SHA-256
- [Iteration 33 report](ITERATION_33_REPORT.md), independently completed INSEE codelist gate

Reports/raw archives stay in ignored local storage under existing policy.
Public recorded XML/provenance, synthetic fixture and source documents are
committed. XML entity bytes after requests content decoding are preserved,
not relabelled as exact wire bytes. Existing raw and reports are not overwritten.
Offline reproduction: `PYTHONPATH=src`, then run
`scripts/verify_api_metadata.py --fixture --source imf-cpi`.
Any live reproduction consumes a new request budget; this task made no repeat.

## Material changes

- `connectors/sdmx.py`: IMF metadata-only client and exact public HTTPS root in existing bounded SDMX wrapper. A dataflow GET method only; no observation/private/auth methods.
- `discovery/sdmx_metadata_validation.py`: explicit `imf-cpi` selection, independent iteration=34 budget, IMF.STA/CPI identity and unpinned returned latest version. Existing source/error/XML/size contract is reused.
- `storage/api_responses.py`: register IMF's source agency/official API host for existing write-once manifest/hash read-back and credential refusal. No source-specific response rewriting.
- `discovery/source_registry.py`: documented public access, PARTIAL metadata-only implementation/live scope with actual version; avoids claiming private/general API access.
- `tests/test_sdmx_connectors.py`, `test_sdmx_metadata_checks.py`, `test_source_registry.py`: public root/structure negotiation/no-auth request; source-separated success/error/empty/wrong-ID/HTML/JSON/oversize/tamper/credential/iteration-budget regressions; recorded source/hash validation. Synthetic IMF scenario IDs remain distinct from real CPI identifiers.
- `tests/fixtures/sdmx_metadata/imf-cpi.xml`, `recorded_imf_cpi.xml` and provenance: synthetic vs live evidence is explicit. Git's existing recorded-XML byte-preservation attributes apply.
- `connectors/IMF.md`, product/implementation/execution plans, API keys guidance, catalogue/audit/status/validation matrix, SDMX/archive documents, decision log and AGENTS: official public root/auth findings, actual results, current 13 API archive clients and consumed two-iteration exception. No key setting was added.

## Verification

- Live-before engineering suite: **1,084 passed, 1 skipped, 0 failed (73.65 seconds)**.
- Changed Python Ruff PASS and IMF synthetic metadata/archive/read-back PASS.
- Final full offline suite including INSEE and IMF recorded fixtures/current registry:
  **1,085 passed, 1 skipped, 0 failed (1,134.89 seconds as reported by pytest)**.
  This elapsed time is an observed test run, not a performance benchmark or improvement claim.
- Final changed Python Ruff PASS. Skip is the existing Windows symlink creation limitation.
- Repository-local unique basetemp was used in approved shells; no ACL or user Temp changes.
- Final actual configured credential nonexposure scan PASS across **36 changed and produced files**, including both iterations' reports/raw/manifests. `git diff --check` PASS. Staged recorded-blob hash checks are also required before feature commit; credentials/`.env` remain unchanged and no key was sent.

## Security, scope and remaining decisions

The two authorized iterations made **two metadata HTTP requests total**:
INSEE one and IMF one, no retries. Census/BLS requests zero. Gate U NOT PASSED
and the prior INSEE IPC DSD 404 remain historical failures. Neither was recalled.
TLS verification, redirect refusal, 8 MiB/30-second bounds and raw write-once
storage remain. Error text/private headers/credentials are not copied to reports.
IMF published-data terms and third-party restrictions are recorded; this task
does not publish data, imply endorsement or grant commercial redistribution.

No observations, transformations, XLSX, natural-language workflow, authenticated
IMF access or all-source completion is claimed. Future source work requires a
separate numbered task; BOJ, dataset/DSD expansion and the old INSEE DSD remain
possible choices. No human decision is needed to complete these two scoped
metadata gates; selecting a next task or integrating into main is a human choice.
No main merge, push, deployment or Iteration 35 was performed.
