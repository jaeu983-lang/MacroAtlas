# System Guidelines

## 1. Goal
Create a reproducible platform that first discovers international statistical data and its metadata, then retrieves actual observations through documented APIs.

## 2. Two primary systems

### A. Discovery
Find dataflows, datasets, indicators, series, dimensions, code lists, definitions, units, frequencies, geographic coverage, temporal coverage, and API documentation. Discovery may use official catalogues, SDMX metadata endpoints, official APIs, and permitted web search.

### B. Ingestion
Fetch observations for an identified series using an official documented API. Store request parameters, retrieval time, source identifier, response status, and validation results.

The systems are logically separate but share a metadata catalogue. Discovery must not assume every discovered series is immediately downloadable. Ingestion must not guess unknown identifiers or endpoints.

## 3. Metadata model
Keep source metadata intact and add normalized fields where possible:

- `source_agency`
- `dataset_id`
- `dataflow_id`
- `series_id`
- `indicator_name`
- `definition`
- `dimensions`
- `code_lists`
- `unit`
- `frequency`
- `geo_coverage`
- `time_coverage`
- `seasonal_adjustment`
- `price_basis`
- `source_url`
- `api_documentation_url`
- `retrieved_at`
- `metadata_version`
- `common_concept_id`
- `mapping_status`
- `mapping_rationale`

Not every source exposes every field. Missing metadata must remain explicitly unknown, not be fabricated.

## 4. Cross-source mapping
Classify links as:
- `exact`: same source-defined concept and compatible dimensions
- `comparable`: concept matches but one or more transformations/qualifications are needed
- `related`: related concept, not directly interchangeable
- `unmatched`: no reliable mapping
- `review_required`: evidence is insufficient

Name similarity is a candidate-generation method only. Mapping decisions must consider definitions, units, frequency, coverage, methodology, revisions, and dimension codes.

## 5. Raw and normalized data
Keep raw API payloads or reproducible raw extracts separate from normalized tables. Transformations must be documented and reproducible. Distinguish zero, missing, suppressed, not applicable, and unavailable values where source metadata permits.

## 6. API connectors
Each connector should document:
- official source and documentation URL
- authentication requirements
- endpoint and parameters
- pagination and rate limits
- timeout/retry behavior
- error mapping
- expected response schema
- source attribution and licensing
- test fixtures with mocked responses

Never assume a public website has a stable API. Verify official documentation first.

## 7. Reliability
- Use timeouts and honor server `Retry-After` before resuming. A stage sends one request by default;
  retries require a persisted attempt budget. Prefer explicit resume over hidden connector retries.
  Add bounded exponential backoff only when the source policy, request budget, and execution model
  are specified and tested.
- Log metadata retrieval and data ingestion separately.
- Store timestamps in ISO 8601 UTC unless the source requires a local time.
- Make ingestion idempotent where feasible.
- Keep a change log for metadata and mapping revisions.
- Add regression tests before replacing existing behavior.

## 8. Initial technology choices
- Python 3.11+
- `venv` for an isolated environment
- `pytest` for tests
- `requests` for HTTP
- `pandas` for tabular processing
- SQLite for the initial local catalogue
- Git for versioning
- PowerShell Task Scheduler scripts for local automation

Add dependencies only when they solve a concrete need.

## 9. Approval policy
Automated improvement may edit code and run tests on a dedicated branch. It may not merge, publish, deploy, delete source data, change credentials, or alter external permissions. Human review is required before integration into the main branch.
