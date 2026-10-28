# e-Stat API v3.0 client

## Official contract

- Overview: <https://www.e-stat.go.jp/api/en/api-info>
- API specification: <https://www.e-stat.go.jp/api/en/api-info/api-spec>
- User guide: <https://www.e-stat.go.jp/api/api/api/index.php/en/api-info/api-guide>
- JSON route root: `https://api.e-stat.go.jp/rest/3.0/app/json`
- Authentication: an Application ID is issued from the registered account's MyPage and sent as `appId`.
- Implemented GET methods: `getStatsList`, `getMetaInfo`, and `getStatsData`.
- API v3.0 documents XML, JSON and CSV functions. This client intentionally requests JSON only.

## MacroAtlas boundary

`EStatClient` reads `Settings.estat_app_id` and constructs method paths from a fixed allowlist.
Credentials are not accepted as method parameters. Requests require
`MACROATLAS_NETWORK_ENABLED=true`, use a 5/20 second connect/read timeout, a 30 second response
budget, a one MiB response limit, no redirects, default TLS verification, and `trust_env=False`.
HTTP 401/403 is an authentication review; temporary HTTP/transport failures are retryable without
immediate retry; redirects stop.

JSON is returned as a sanitized `JsonApiResponse`, with a safe endpoint, method, HTTP status and
UTC retrieval timestamp. The payload is not a byte-exact raw archive; sensitive fields and any
echo of the configured Application ID are redacted. Table semantics, pagination, licensing,
units, frequency and revision metadata are not normalized by this client. General workflow and
observation ingestion are not implemented. Iteration 31 verified one live getStatsList call with
`lang=E, limit=1`, STATUS=0 and one table entry, sanitized archive and hash read-back. The
metadata-only CLI is `scripts/verify_api_metadata.py --live --source estat`; each execution consumes
a fresh one-request budget. See the [Iteration 31 report](../history/ITERATION_31_REPORT.md).

## Local credential setup

Enter the value only in the ignored repository-root `.env` file:

```ini
ESTAT_APP_ID=your_e-Stat_Application_ID
MACROATLAS_NETWORK_ENABLED=false
```

`Settings.from_project_env(Path.cwd())` reads the file and lets process environment variables
override it. Keep the network switch false until intentionally making a request. Never put the
value in `.env.example`, source code, tests, logs or documents.

## Evidence

Official documentation was reviewed for v3.0 JSON routes, the three GET functions, and Application
ID registration. Local mocked HTTP tests exercise the request and redaction behavior. No e-Stat
request or credential validation was performed for this implementation.
