# IMF public metadata — Iteration 34

## Official evidence checked 2026-10-25

- [IMF API page](https://data.imf.org/en/Resource-Pages/IMF-API) identifies SDMX 2.1/3.0 and links its support guides. It warns of maintenance October 24–26. Its Swagger link redirects to sign-in; that alone does not establish data API auth requirements.
- [Official MATLAB support](https://datasupport.imf.org/knowledge?id=knowledge_category&sys_kb_id=7472009697bc4390d4f0b437f053afa8&category_id=9959b2bc1b6391903dba646fbd4bcb6a) explicitly gives public root `https://api.imf.org/external/sdmx/2.1` and separates public from internal provider setup.
- [Official R support](https://datasupport.imf.org/knowledge?category_id=9959b2bc1b6391903dba646fbd4bcb6a&id=knowledge_category&sys_kb_id=11a9866397604f54d4f0b437f053affb) identifies `IMF.STA,CPI` and public-user queries. Authentication is described separately for elevated staff/partner access.
- [Official Python support](https://datasupport.imf.org/knowledge?category_id=9959b2bc1b6391903dba646fbd4bcb6a&id=knowledge_category&sys_kb_id=5ca208d697bc4390d4f0b437f053af9e) also distinguishes public from authenticated use. It uses the IMF_DATA provider alias rather than spelling out the endpoint.
- [SDMX 2.1 web-service contract §4.3](https://sdmx.org/wp-content/uploads/SDMX_2-1-1-SECTION_07_WebServicesGuidelines_2013-04.pdf) defines resource/agency/resource-ID/version, including dataflow and latest. This is the historical 2.1 contract matching IMF's explicit 2.1 root; newer standard development lives in the linked SDMX GitHub repository.

The support pages required browser JavaScript rendering; the web reader returned
only loading placeholders. Browser read-only navigation exposed their public
content. No sign-in, hidden endpoint inspection, token acquisition, installation,
account creation or elevated/private provider access was performed.

## Bounded selection and limits

Assemble the documented root, official `IMF.STA`/`CPI` identifiers and standard
2.1 structural query template:

`https://api.imf.org/external/sdmx/2.1/dataflow/IMF.STA/CPI/latest`

This composition is based on the official provider guide plus SDMX contract;
we did not read an authenticated Swagger operation. Its actual response is a
separate canary result. No version number is invented: request latest, require a
nonempty returned version, and preserve it with the raw response.

One metadata GET maximum, retry zero, concurrency one; no observations, no
references query, no all-catalogue expansion. Existing transport enforces exact
HTTPS host/root, 8 MiB/30-second bounds, TLS verification and redirects refused.
Negotiate `application/vnd.sdmx.structure+xml;version=2.1`. Validate IMF source,
exact request, root/namespace, message ID, selected dataflow agency/ID/version,
name and complete DSD reference, then write-once archive/hash read-back.
Any HTML/JSON/error/empty/wrong-ID response fails closed. No arbitrary key/header
authentication is added; a public access failure is not bypassed.

No numeric API quota was found in reviewed public material; one request is a
local budget, not a claim about an IMF limit. The official maintenance warning
means a transient failure may occur; this task will not retry.

## Terms and scope

[IMF copyright and usage](https://www.imf.org/en/about/copyright-and-terms)
distinguishes statistical-data reuse from general content, requires attribution
and integrity, preserves third-party restrictions and limits automated bulk
downloads. Commercial reuse requires separate review/permission under the
published terms. This task is one local metadata validation, no bulk collection
or publication. No broad redistribution permission is inferred.

Fixtures are synthetic unless explicitly recorded with provenance/hash.
Existing synthetic IMF scenario IDs do not establish real provider identifiers.
No general ingestion, CPI series semantics, price-base comparability, all-IMF
coverage, private API access, SDMX 3.0 or normalized observation storage is covered.
Actual result and remaining action are recorded in the Iteration 34 report.
