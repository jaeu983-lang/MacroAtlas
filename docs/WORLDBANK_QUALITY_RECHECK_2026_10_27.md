# World Bank GDP quality-policy recheck — 2026-10-27

This is a read-only recheck of the already preserved USA/WDI `NY.GDP.MKTP.CD` task
`0f968a54-9855-439c-aaf2-bb7022fb5c8c` for 2020–2022. It did not make an HTTP request,
write to `data/catalog.sqlite`, replace the archived validation, or alter either source artifact.

The task and artifact records were read from SQLite in read-only mode. The captured response and
request manifest were verified against their recorded SHA-256 hashes, then the saved response was
parsed and evaluated with `worldbank_gate_a_v2`.

| Check | Result |
|---|---|
| Raw SHA-256 | `219e79f17e08a93d64f747f3cdb7376d09349e5c8525d24f316532b86cccd6b1` |
| Request manifest SHA-256 | `c8df61cb996e3a5fa3049bc3a4d7fbe3dc042fd2a6d6d22fc1d4d861359ebaff` |
| Quality result | `passed`; no issues |
| Rows / missing values / negative GDP values | 3 / 0 / 0 |
| Unit and frequency | Unknown; warning retained |

This confirms only that the new negative-value guard does not reject this preserved sample. The
original database validation remains version 1; this report does not rewrite historical task
evidence. Unit/frequency metadata, broader outlier review, revision history, and cross-source
equivalence remain outside the verified scope.
