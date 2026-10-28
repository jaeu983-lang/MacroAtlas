# Iteration 32 metadata route audit

Checked 2026-10-25. Official documentation research is separate from HTTP canary
evidence. The selected paths below request one structural resource, no observations,
no linked-resource traversal, no retries. Existing 8 MiB / 30-second transport limits,
TLS checking, redirects refused, sequential requests and archive contracts apply.

| Source | Fixed selection / route after existing official root | Official identity and route evidence |
|---|---|---|
| BIS INT-02 | `structure/dataflow/BIS/WS_TC/2.0` | [v2 specification](https://stats.bis.org/api-doc/v2/) and [BIS series page](https://data.bis.org/topics/TOTAL_CREDIT/BIS,WS_TC,2.0/Q.ID.N.A.M.USD.A); API v2 path, selected flow version 2.0 |
| OECD INT-03 | `dataflow/OECD.SDD.NAD/DSD_NAMAIN1@DF_QNA/1.1` under `/public/rest/v1` | [v1 Swagger](https://sdmx.oecd.org/public/swagger/index.html?urls.primaryName=v1), [official QNA API builder](https://data-explorer.oecd.org/vis?df%5Bag%5D=OECD.SDD.NAD&df%5Bds%5D=dsDisseminateFinalDMZ&df%5Bid%5D=DSD_NAMAIN1%40DF_QNA&df%5Bvs%5D=1.1&dq=Q&pg=0&snb=14&tm=real+gdp); builder uses version-free REST entry point, existing client uses versioned v1; no claim of reachability before canary |
| ECB EU-01 | `datastructure/ECB/ECB_EXR1/1.0` | [official metadata examples](https://data.ecb.europa.eu/help/api/metadata-examples) gives this exact DSD/version; no references query, default none |
| Eurostat EU-02 | `dataflow/ESTAT/NAMA_10_GDP/1.0` | [structure queries](https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1/structure-queries) and [data query guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1/data-query); dataflow is non-versioned, 1.0 explicitly supported |
| Bundesbank EU-03 | `metadata/dataflow/BBK/BBEX3` | [official metadata examples §3](https://statistiken.bundesbank.de/statistiken-en/help-991452?article=bundesbank-sdmx-web-service-api-991448); no version in route, require a nonempty returned version without inventing a version pin |
| INSEE EU-05 | `datastructure/FR1/IPC-2015-COICOP/1.0` | [service page](https://www.insee.fr/en/information/2868055), [user guide §IV pp15–16](https://www.insee.fr/en/statistiques/fichier/2868055/BDM_serviceweb_SDMX_V2_2_userguide.pdf); exact example DSD, FR1 and only version 1.0 documented |

## Access, limits and permitted use

- BIS: existing documented public API/no key profile retained. [Permitted use](https://www.bis.org/about/legal/permitted-use-statistics) requires attribution and non-misleading use; API access can be limited or suspended. Numeric quota not established; local budget is one request.
- OECD: [API guide](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html) documents public query-builder access subject to OECD terms. [FAQ](https://www.oecd.org/en/data/insights/data-explainers/2024/09/OECD-DE-FAQ.html) reports 60 queries/hour; [platform status](https://www.oecd.org/en/data/insights/data-explainers/2025/02/OECD-Data-Explorer-News.html) warns about bot challenges and intermittent service issues. One direct public GET, no sign-in or challenge bypass. Global authentication profile remains unknown until evidence supports a narrower update.
- ECB: public metadata examples and existing no-key profile; [API syntax](https://data.ecb.europa.eu/help/api/metadata) documents references=none default. Numeric quota not established in reviewed material; one request only. [ESCB reuse policy](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.pl.html) requires source attribution.
- Eurostat: existing public/no-key dissemination profile; [API guide](https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction) and [copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice) apply. One resource avoids async/bulk operation; no global quota inferred.
- Bundesbank: official help supplies direct public metadata links and indicates freely available content subject to its linked [terms](https://www.bundesbank.de/en/homepage/user-information/terms-of-use-642972?index=2). A one-off uncredentialed request follows that example; global auth remains unknown unless the selected request succeeds. Metadata is XML only, even though observation formats include JSON. Documented 200-series CSV/ZIP and 413 handling are outside this metadata request; numeric metadata quota not established.
- INSEE: user guide explicitly separates direct `bdm.insee.fr` HTTPS access from `api.insee.fr` portal sign-in. Use direct BDM only; no portal credentials. [Legal/reuse notice](https://www.insee.fr/en/information/2409130) requires attribution, known update date and preserving meaning; limit automated request frequency. Guide's 400 IDBANK / 2000 series limits concern data queries; metadata numeric quota not established. One old documented DSD may have been retired; a 404 is failure with no fallback request.

## Response contract and parser reuse

All six requests explicitly negotiate `application/vnd.sdmx.structure+xml;version=2.1`.
Validate HTTP 200, exact selected source/URL/operation, reviewed XML media type,
SDMX 2.1 message root and structure namespace, nonempty message ID, exactly one
selected resource, matching agency/ID/pinned version, name and non-stub contents.
Dataflows require a complete DSD reference; DSDs require distinct named dimensions.
Error envelopes, HTML, JSON (including error JSON), empty/malformed/oversized XML,
DTD/entities, duplicate resources and wrong namespaces fail closed. JSON success
parsing and SDMX 3.0 metadata are outside this iteration's negotiated contract.

`metadata.adapters.parse_sdmx_structure` reuses the existing structure parser;
the new strict envelope checks run before it. Unfetched DSDs/codelists remain
explicit unresolved references. No labels establish statistical equivalence.
Archives preserve HTTP entity bytes after requests decoding, not wire bytes.
Configured credentials in SDMX bytes cause archive refusal; keys are never sent.

Synthetic fixtures explicitly mark their origin. Any recorded fixture is copied
only after credential scanning and records URL, UTC retrieval time, content type,
representation and SHA-256 separately. Live source sub-gates require the contract
and manifest/hash read-back together. See the Iteration 32 report for actual results.
