# Iteration 33 — INSEE structural metadata recovery

The Iteration 32 `datastructure/FR1/IPC-2015-COICOP/1.0` request returned 404.
It remains a failed historical attempt; a different resource does not repair or
prove the old DSD's availability.

The official [service page](https://www.insee.fr/en/information/2868055) still
links the [user guide](https://www.insee.fr/en/statistiques/fichier/2868055/BDM_serviceweb_SDMX_V2_2_userguide.pdf).
Section IV, pages 15–16, explicitly documents resource/agency/identifier/version,
FR1 and version 1.0, and the `codelist/FR1/CL_NATURE` example. This iteration's
independent bounded request is therefore:

`https://bdm.insee.fr/series/sdmx/codelist/FR1/CL_NATURE/1.0`

This is a documented codelist metadata request, not a guessed replacement DSD.
The guide distinguishes direct BDM HTTPS access from the API portal requiring
sign-in. Use direct HTTPS only; do not add a key or portal session. Reuse follows
the [INSEE legal notice](https://www.insee.fr/en/information/2409130): acknowledge
the source, retain known update dates and preserve meaning. No numeric metadata
quota is established in reviewed material. Local budget: one GET, zero retries,
one request at a time, 8 MiB and 30-second bounds, redirects refused.

Negotiate SDMX-ML structure 2.1. Preserve the envelope/source/ID checks from
Iteration 32 and additionally require a nonempty Codelist, distinct nonempty
code IDs and nonempty code labels. The existing parser retains all language
labels without translating or interpreting statistical equivalence.
Empty/duplicate codes, missing labels/IDs, error/HTML/JSON envelopes and
source/version mismatches do not pass. Save/hash/read-back uses the common
write-once archive and credential refusal contract.

Select `--source insee-nature` explicitly in `scripts/verify_api_metadata.py`.
The old `insee` selection and its Iteration 32 result remain distinct. The runner
rejects mixing numbered iteration budgets and keeps BEA/e-Stat defaults unchanged.
Results and remaining limitations belong in the Iteration 33 report.
