# BEA Data API client

## Official contract

- API documentation: <https://apps.bea.gov/API/docs/index.htm>
- API user guide: <https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf>
- Fixed request URI: `https://apps.bea.gov/api/data`
- Authentication: registered 36-character UserID, supplied as the documented `UserID` query parameter.
- Required request fields: `UserID`, `method`, `ResultFormat=JSON`.
- Supported methods: dataset list, parameter list, parameter values, filtered parameter values, and data retrieval.
- BEA says throttling and usage limits apply; this client does not retry automatically. Consult the current official guide for current limits.

## MacroAtlas boundary

`BEAClient` reads `Settings.bea_api_key` and only calls the fixed HTTPS endpoint. Credentials are
not accepted as method parameters. Requests require `MACROATLAS_NETWORK_ENABLED=true`, use a
5/20 second connect/read timeout, a 30 second response budget, a one MiB response limit, no
redirects, default TLS verification, and `trust_env=False`. HTTP 401/403 is an authentication
review; temporary HTTP/transport failures are retryable without immediate retry; redirects stop.

JSON is returned as a sanitized `JsonApiResponse`, with a safe endpoint, method, HTTP status and
UTC retrieval timestamp. The payload is not a byte-exact raw archive; sensitive fields and any
echo of the configured UserID are redacted. Dataset semantics, pagination, licensing, units,
frequency and revision metadata are not normalized by this client. General workflow and observation
ingestion are not implemented. Iteration 31 verified one live GetDataSetList call (13 entries),
source-envelope validation, sanitized archive and hash read-back. The metadata-only CLI is
`scripts/verify_api_metadata.py --live --source bea`; one call requires a fresh request budget.
Synthetic and recorded sanitized metadata fixtures are distinct. See the
[Iteration 31 report](../history/ITERATION_31_REPORT.md).

## Local credential setup

Enter the value only in the ignored repository-root `.env` file:

```ini
BEA_API_KEY=your_BEA_UserID
MACROATLAS_NETWORK_ENABLED=false
```

`Settings.from_project_env(Path.cwd())` reads the file and lets process environment variables
override it. Keep the network switch false until intentionally making a request. Never put the
value in `.env.example`, source code, tests, logs or documents.

## Evidence

Official documentation was reviewed for the endpoint, required UserID, methods, JSON format, and
registration. Local mocked HTTP tests exercise the request and redaction behavior. No BEA request
or credential validation was performed for this implementation.
