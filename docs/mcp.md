# MCP server

`mcp_server/server.py` exposes the scraper as a Model Context Protocol server
over streamable HTTP (default `0.0.0.0:8080`). External Claude sessions
register it and call its tools to inspect, modify, and run the scraper without
shelling into the container.

This page is the canonical reference for what those tools accept and return.

## Boot

```bash
python -m mcp_server.server          # local
docker compose --profile mcp up -d   # container, image job-scraper
```

Environment variables:

| Var               | Default       | Purpose                                 |
|-------------------|---------------|-----------------------------------------|
| `MCP_HOST`        | `0.0.0.0`     | Bind address                            |
| `MCP_PORT`        | `8080`        | Bind port                               |
| `PROXY_URL` | none, required | Proxy URL for scrapes. Empty means direct connection. Not set stops scrapes |
| `PROXY_TEST_URL`  | `https://api.ipify.org?format=json` | URL `test_proxy_connection` fetches by default |
| `PROXY_TEST_TIMEOUT_SEC` | `25` | Per-request timeout for that probe |

## Registering from a client Claude session

Add an entry to that container's `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "job-scraper": {
      "type": "http",
      "url": "http://scraper-mcp:8080/mcp"
    }
  }
}
```

Hostname `scraper-mcp` assumes both containers share the same Docker network.
Adjust if running elsewhere.

## Tool catalog

### `list_sites`

Read-only. Inspect resolved config without running anything.

**Args**: none.

**Returns**:

```json
{
  "sites": [
    {
      "name": "jobstreet",
      "enabled": true,
      "url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1",
      "sample_url": "https://id.jobstreet.com/id/data-analyst-jobs?daterange=1"
    },
    ...
  ]
}
```

`sample_url` is the template formatted with the placeholder keyword
`data analyst`. The job settings hold no keywords, so there is no keyword list
here: every `scrape_jobs` call names its own.

Use this first to confirm which `sites` are active before calling
`scrape_jobs` or proposing a `update_config` patch.

### `get_config`

Read-only. Returns the job settings from Mongo, with their version.

**Args**: none.

**Returns**:

```json
{
  "version": 4,
  "updated_at": "2026-11-02T01:00:00+00:00",
  "updated_by": "ui",
  "settings": {
    "fields": ["title", "company", "location", "url"],
    "sites": {
      "jobstreet": {
        "enabled": true,
        "limit": 3,
        "max_age_hours": 72,
        "filter": {"location": ["jakarta"]},
        "url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1"
      }
    }
  },
  "job_fields": ["site", "matched_keyword", "title", "..."],
  "mandatory_fields": ["site", "matched_keyword", "title", "company", "url"],
  "location_options": {
    "jobstreet": [{"label": "Jakarta", "value": "Jakarta Raya"}, "..."],
    "glints": [{"label": "Jakarta", "value": "78d63064-78a1-4577-8516-036a6c5e903e"}, "..."],
    "linkedin": [{"label": "Jakarta", "value": "Jakarta, Indonesia"}, "..."]
  }
}
```

- `job_fields`: every field name the top-level `fields` list accepts, in scraper order
- `mandatory_fields`: fields saved for every job whatever the settings say
- `location_options`: the fixed city list per site (from `scraper/api/locations.py`).
  `label` is what the UI shows, `value` is what goes into `sites.<name>.api.locations`.
  Sites without an API city list (indeed, upwork) are absent

Returns `{"error": "..."}` when Mongo is down or the document is missing.

Always call `get_config` before `update_config` to know the current shape so
your patch is minimal. A stored document that still has global `limit`,
`concurrency`, `max_age_hours` or `filter` is migrated into the sites on the
first read (a `default_fields` key is renamed to `fields`, and per-site
`fields` overrides are dropped), with a new version and `updated_by: "migration"`, after a copy of
the original is kept as `active_pre_migration_backup` (see
[`configuration.md`](configuration.md#migration-from-global-values)).

### `get_scrape_response_structure`

Read-only. Returns canonical response contract for `scrape_jobs`.

**Args**: none.

**Returns**:

```json
{
  "tool": "scrape_jobs",
  "version": "1.0.0",
  "job_fields": ["site", "matched_keyword", "title", "..."],
  "top_level_fields": ["ok", "keywords", "requested_sites", "exit_code", "results", "errors"],
  "optional_top_level_fields": ["raw_results", "filtered_results"],
  "site_result_fields": ["site", "keyword", "fields", "max_age_hours", "filter", "count", "jobs"],
  "error_fields": ["keyword", "site", "reason", "attempts"],
  "sample": { "...": "example payload" }
}
```

Use this when you need strict output formatting in downstream automations.
The shape of `attempts` is under [`scrape_jobs`](#scrape_jobs).

### `update_config`

Write. Applies a patch to the job settings, and validates the result.

**Args**:

```json
{ "patch": { }, "expected_version": 4, "source": "mcp" }
```

- `patch`: top-level keys (`fields`, `sites`) are replaced whole. `fields` is one list for every site. `sites` merges by site name. Each field of a site is replaced whole, so send the full `filter` or `api`. A `null` removes the key: `max_age_hours: null` means no age cut for that site. `limit` cannot be removed, every site needs one
- `expected_version`: optional. The version you read. A mismatch saves nothing
- `source`: `ui` or `mcp`. Kept with the version

Only job setting keys are allowed: `fields`, `sites`. `limit`, `max_age_hours` and `filter` are per site only, so a top-level `limit`, `concurrency`, `max_age_hours`, `filter`, `keywords`, `default_fields` or `proxy` is refused with `not a job setting: <key>`. Keywords are not stored: pass them to `scrape_jobs` on every call. Concurrency comes from the `SCRAPER_CONCURRENCY` env var. Field names in `fields` that are not in `get_config`'s `job_fields` are refused with reason `invalid`. A site has no fields of its own: `sites.<name>.fields` is refused with reason `invalid` and `sites.<name>.fields is no longer supported, use the top-level fields`.

**Returns** (success):

```json
{ "ok": true, "version": 5, "updated_at": "...", "updated_by": "mcp", "settings": { } }
```

**Returns** (failure, nothing changed):

```json
{ "ok": false, "reason": "invalid", "message": "sites.glints.limit must be a whole number from 1 to 200, got -5" }
```

`reason` is `invalid`, `conflict`, or `unavailable`.

#### Patch examples

Change the job fields for every site:
```json
{"patch": {"fields": ["title", "company", "url", "salary"]}}
```

Tighten recency on one site:
```json
{"patch": {"sites": {"glints": {"max_age_hours": 6}}}}
```

Raise how many jobs one site returns:
```json
{"patch": {"sites": {"indeed": {"limit": 10}}}}
```

Disable LinkedIn for the next runs:
```json
{"patch": {"sites": {"linkedin": {"enabled": false}}}}
```

Add a search location to one site's filter (the whole filter is replaced, so send every location and key):
```json
{"patch": {"sites": {"jobstreet": {"filter": {"location": ["jakarta", "bandung", "surabaya"]}}}}}
```

Change the filter of a site:
```json
{"patch": {"sites": {"glints": {"filter": {"employment_type": "internship"}}}}}
```

Turn a site's filter off:
```json
{"patch": {"sites": {"upwork": {"filter": {}}}}}
```

Turn a site's age cut off:
```json
{"patch": {"sites": {"glints": {"max_age_hours": null}}}}
```

Replace LinkedIn URL template (e.g. switch to a different geoId):
```json
{"patch": {"sites": {"linkedin": {"url_template": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword}&geoId=104884688&f_TPR=r86400&start=0"}}}}
```

#### Validation

Every patch is merged, then run through `scraper.config_loader.parse_job_settings_into_app_config` before
anything is saved. The same rules listed in
[`configuration.md`](configuration.md) apply: a missing or malformed site
`limit`, top-level global keys, missing required keys, invalid URL placeholders, etc. all return
`{ok: false, reason: "invalid", message: …}`.

### `test_proxy_connection`

Read-only network probe. Performs one HTTPS GET through the proxy using the
same curl_cffi stack as the scraper HTML downloaders (so HTTP, HTTPS, and SOCKS5 proxy
URLs work the same as in a scrape).

**Args** (all optional):

```json
{
  "proxy_url": "socks5://127.0.0.1:1080",
  "url": "https://api.ipify.org?format=json"
}
```

- `proxy_url`: when omitted, uses `PROXY_URL`. If both are missing,
  returns `{ok: false, error: ...}`.
- `url`: target URL to fetch (must be `http` or `https`). Default comes from
  `PROXY_TEST_URL` or ipify as in the env table above.

**Returns** (success example):

```json
{
  "ok": true,
  "proxy_redacted": "user:***@proxy.example.com:1080",
  "source": "config",
  "test_url": "https://api.ipify.org?format=json",
  "duration_ms": 842.5,
  "http_status": 200,
  "egress_ip": "203.0.113.1",
  "response_excerpt": "{\"ip\":\"203.0.113.1\"}"
}
```

`proxy_redacted` masks proxy passwords. `source` is present only when the
proxy URL came from `PROXY_URL`. On failure, `ok` is false and `error` describes
validation, connection, or non-200 HTTP.

The `docs:/app/docs:ro` mount makes the markdown reference docs (this file,
`runbook.md`, `configuration.md`, `sites.md`, etc.) live-readable from inside
the container. Edit any doc on the host and the next read inside the
container sees it — no rebuild needed. Drop the mount for production
deployments where docs aren't expected to change at runtime.

### `scrape_jobs`

Run the scraper. Triggers fetches across `(keyword, site)` pairs and returns
aggregated results.

**Args** (`keywords` required, the rest optional):

```json
{
  "keywords": ["data analyst"],
  "sites": ["linkedin", "indeed"],
  "save_run": true,
  "include_payloads": false
}
```

- `keywords`: required list of keywords to scrape. The job settings hold no
  keywords, so there is no fallback. Each keyword is trimmed and blank ones
  are dropped. `null`, `[]` or only blank keywords is refused (see below).
- `sites`: list of site names to scrape. Omitted = all enabled sites.

In Python, `sites` is the only positional parameter; `keywords` and the rest
are keyword-only: `scrape_jobs(["glints"], keywords=["data analyst"])`.
- `save_run`: store the run in MongoDB. Omitted = `true`. The job-match search
  box and the scraper UI send `false`, so their results are shown once and stay
  out of the scrape history. `mongo_id` is then `null`.
- `include_payloads`: add `raw_results` and `filtered_results` to the response.
  Omitted = `false`. Off by default because both carry every site's full payload,
  which makes the response much bigger; the job-agent backend keeps the smaller
  response. The scraper UI sends `true` to show each run's raw and filtered data.

**Returns**:

```json
{
  "keywords": ["data analyst"],
  "requested_sites": ["linkedin", "indeed"],
  "exit_code": 0,
  "results": [
    {
      "keyword": "data analyst",
      "sites": [
        {
          "site": "linkedin",
          "fields": ["title", "company", "url", ...],
          "max_age_hours": 24,
          "filter": {"location": ["jakarta"]},
          "count": 2,
          "jobs": [...]
        },
        {"site": "indeed", ...}
      ]
    }
  ],
  "errors": [
    {"keyword": "data analyst", "site": "glints", "reason": "fetch failed"}
  ]
}
```

`results` is always grouped by keyword first, then site. `errors` collects
any pair whose fetch failed, that was skipped (`skipped: site has no entry in the
job settings`), that crashed (`crashed: <ExceptionType>`), or that the runner gave
no result for (`scraper returned no result for this pair (exit code 1)`, when the
site selection was invalid).

An error whose HTML download failed (`fetch failed`) also has `attempts`: one
`{downloader, code, detail}` entry per HTML downloader tried, in order.

```json
{
  "keyword": "data analyst",
  "site": "glints",
  "reason": "fetch failed",
  "attempts": [
    {"downloader": "curl_cffi", "code": "http_403", "detail": "status=403"},
    {"downloader": "cloudscraper", "code": "challenge", "detail": "title=Just a moment..."},
    {"downloader": "playwright", "code": "timeout", "detail": "..."}
  ]
}
```

- `downloader`: `curl_cffi`, `cloudscraper` or `playwright`
- `detail`: more text about the outcome, or `null`
- `code`: one of

| Code            | Meaning                                                  |
|-----------------|----------------------------------------------------------|
| `http_<status>` | site rejected the request (e.g. `http_403`)              |
| `challenge`     | anti-bot wall (`detail` is the matched title or marker)  |
| `timeout`       | network or page-load timeout                             |
| `runtime_error` | unexpected exception (`detail` is the class and message) |
| `not_installed` | HTML downloader dependency missing                       |

Runs saved before the rename from fetchers to HTML downloaders carry the key
`fetcher` instead of `downloader`.

**Returns** (no keywords): when `keywords` is `null`, empty or only blank, nothing runs, no
status is written and nothing is saved to Mongo:

```json
{
  "ok": false,
  "keywords": [],
  "requested_sites": ["linkedin", "indeed"],
  "exit_code": 1,
  "results": [],
  "errors": [{"keyword": null, "site": null, "reason": "keywords are required"}],
  "mongo_id": null
}
```

`requested_sites` echoes the `sites` argument (`[]` when omitted). Leaving the
`keywords` argument out entirely is rejected by the MCP argument check before
the tool runs.

Results come straight back from `scraper.runner.scrape_all_sites`. Nothing is written to disk.

With `include_payloads: true` the response also has two optional lists, each
entry `{"keyword": "...", "site": "...", "payload": {...}}`:

- `raw_results`: each site's payload before max-age, filter and limit
- `filtered_results`: each site's final payload, the same one stored in Mongo

Without the flag these two keys are not in the response.

When the job settings cannot be loaded (Mongo is down, the document is missing, or `PROXY_URL` is not set), `scrape_jobs` returns `{"ok": false, "error": "..."}` and scrapes nothing.

## Operational rules for Claude callers

When asked to change scraper behavior at runtime, follow this loop:

1. Call `get_config` (or `list_sites` for a higher-level view).
2. Construct a minimal `patch` reflecting only the user's request.
3. Call `update_config` with that patch and the version from `get_config`.
4. If `ok=false`, surface the `message` to the user — do NOT retry with a
   different patch unless the user agrees. The error is from the same
   validator the scraper itself uses.
5. On success, optionally call `scrape_jobs` to confirm the new config
   produces expected output.

Avoid:

- Sending a full `config` object as a "replacement" — always patch.
- Inventing keys not in [`configuration.md`](configuration.md).
- Modifying URL templates without checking [`sites.md`](sites.md) for the
  site's expected query-param vocabulary.
- Silently retrying on validation errors.

For specific edit recipes (most common user requests mapped to exact
patches), see [`runbook.md`](runbook.md).
