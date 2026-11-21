# Architecture

A short tour of how the pieces fit together. Helpful when proposing
config edits that touch unfamiliar areas, or when adding a new site.

## Package map

```
scraper/                    # library used by the MCP and UI servers
├── runner.py               # orchestrates (keyword, site) pairs through a thread pool
├── config_loader.py        # settings dict → AppConfig dataclass + validation
├── job_settings.py         # JobSettingsStore: Mongo job settings and versions
├── seed_settings.py        # seeds Mongo from seeds/job_settings.yaml
├── types.py                # canonical Job TypedDict + CANONICAL_FIELDS
├── config.py               # static constants (USER_AGENT, CHALLENGE_MARKERS, etc.)
├── log.py                  # get_scraper_logger() (stdout only, no log file), hide_proxy_password()
├── html_downloaders/       # HTML page download layer
│   ├── base.py             # FallbackHtmlDownloader, looks_like_challenge
│   ├── curl_cffi.py        # first attempt: HTTP request that impersonates Chrome
│   ├── cloudscraper.py     # second attempt: cheap HTTP HTML downloader (Cloudflare-aware)
│   └── playwright.py       # last attempt: browser (lazy import, ~280MB Chromium)
├── api/                    # API-first job sources
│   ├── client.py           # ApiClient (one curl_cffi session, paced requests) + ApiError
│   ├── source.py           # ApiSource protocol + search_all(): one search per city, de-duplicated
│   ├── registry.py         # API_SOURCES: site name → API class
│   ├── jobstreet.py        # JobstreetApi: search API + GraphQL job detail
│   ├── glints.py           # GlintsApi: GraphQL search + job detail
│   ├── linkedin.py         # LinkedinApi: guest search, no detail API
│   ├── upwork.py           # UpworkApi: visitor GraphQL search, the search already returns the description
│   ├── window.py           # max_age_hours → days or seconds search window, to_utc_iso()
│   ├── draftjs.py          # draftjs_to_markdown() for Glints job descriptions
│   └── locations.py        # fixed city list per site (label + API value) for the UI picker, served by get_config
└── sites/                  # per-site adapters
    ├── base.py             # Scraper abstract
    ├── _next_data.py       # __NEXT_DATA__ extraction helper
    ├── _dates.py           # parse_to_iso() — locale-aware date parsing
    ├── _filter.py          # project_jobs(), filter_reason(), apply_filter()
    ├── _location.py        # region index for the location filter: loaded from Mongo `wilayah` on first use, cached for the process
    ├── _markdown.py        # html_to_markdown() for job descriptions
    ├── jobstreet.py
    ├── glints.py
    ├── linkedin.py
    ├── indeed.py
    └── upwork.py           # API only: registers Upwork, parse() returns no jobs

mcp_server/                 # MCP HTTP server
├── server.py               # FastMCP, tools: list_sites, get_config, get_scrape_response_structure, update_config, get_scrape_status, insert_scrape_run, get_latest_scrape_run, update_scrape_run, test_proxy_connection, scrape_jobs
├── discord_tools.py        # Discord tools: settings, test, channels, preview_discord_message, send_discord_message
├── discord_settings.py     # DiscordSettingsStore: Mongo `discord_settings`, validation and defaults
├── discord_messages.py     # build_messages(): Discord messages from jobs or text
├── discord_sender.py       # Discord REST calls: bot identity, channel list, post messages
├── mongo.py                # Mongo client + `scrape_runs` helpers (insert, latest, update)
└── __init__.py             # (empty)

ui_server/                  # scraper UI API (FastAPI), see the next section
├── __main__.py             # `python -m ui_server` entry point (uvicorn)
├── app.py                  # create_app(): services, routes, static UI files
├── settings.py             # Settings from `UI_*` env vars
├── dependencies.py         # Services container, session and cross-site checks
├── errors.py               # AppError types + error handlers
├── routes/                 # auth, config, discord, runs, sites
├── schema/                 # request and response models
└── services/
    ├── mcp_gateway.py      # LocalGateway + ScraperClient: calls the MCP tool functions in process
    ├── run_service.py      # RunService: one run at a time, optional Discord notify
    ├── run_record.py       # RunRecord + run and Discord status
    ├── run_detail.py       # RunDetail: record, jobs, failures, payloads
    ├── run_repository.py   # MongoRunRepository: the `ui_runs` run store
    └── auth_service.py     # AuthService, LoginLimiter
```

## Scraper UI API (`ui_server/`)

The UI calls the MCP tool functions in its own process through `LocalGateway`
(`ui_server/services/mcp_gateway.py`), not over HTTP. Sync tools run in a worker
thread with `asyncio.to_thread`, async ones are awaited.

- `GET /api/config`: the job settings plus `location_options`, the same
  `{site: [{label, value}]}` map `get_config` returns.
- `POST /api/runs`: starts one run at a time (409 while one is running) and
  returns its record. UI runs call `scrape_jobs` with `save_run: false` and
  `include_payloads: true`, so they never reach `scrape_runs`.
- `GET /api/runs/latest`: the newest run as `{record, jobs, failures, payloads}`.
  That is the current run when the UI server has one, else the stored run in
  `ui_runs`. `data` is `null` when there is none.
- `GET /api/runs/{id}`: the same detail for the current run or the stored run.
  Any other id returns 404, or 503 `Run storage is unavailable.` when Mongo
  cannot be read. While a run is running, `jobs`, `failures` and
  `payloads` are `[]`.

Detail fields:

- `record`: `id`, `status`, `keywords`, `sites`, `started_at`, `finished_at`,
  `job_count`, `error_count`, `error`, `discord_status`, `discord_sent`,
  `discord_failed`, `discord_error`
- `jobs`: `[{site, matched_keyword, title, company, location, url, posted_at}]`,
  each value a string or `null`
- `failures`: `[{keyword, site, reason}]`
- `payloads`: `[{keyword, site, raw, filtered}]`, `raw` and `filtered` are the
  site payload before and after max age, filter and limit, or `null`

### `ui_runs` collection

When a UI run ends (succeeded, partial or failed), the UI server keeps its
detail in memory and saves it to the `ui_runs` collection in the same Mongo
database (`MONGO_URI`, `MONGO_DB_NAME`). The document `_id` is the run id. Only
the latest run is kept: each save deletes every other document. Discord status
changes after the run update the stored `record` too. The main app backend reads
`scrape_runs`, never `ui_runs`.

The run store uses its own Mongo client with a 1000 ms server selection
timeout. If Mongo is down, the run still works. The first failure logs one
warning and pauses run storage for 30 s: reads and writes skip Mongo in that
time, so they never hold up a request thread or the Discord status. The result
is served from memory only, so it is lost on restart. `GET /api/runs/latest`
returns the in-memory run or `null`.

When a save fails for another reason (for example a detail over Mongo's 16 MB
document limit), it is tried once more without `payloads`, and the size is
logged. If that fails too, every stored run is deleted, so the older run is
never shown as the latest. A Discord status update for a run with no stored
document creates one with the record and empty lists.

## Request flow (per scrape run)

```
seeds/job_settings.yaml → Mongo `job_settings`
   │
   ▼
load_app_config()   →   AppConfig (immutable dataclass)
   │
   ▼
runner.scrape_all_sites(config, requested_sites, keywords)
   │
   ├─ build (keyword, site) cross-product list
   ├─ build one FallbackHtmlDownloader for the run
   │
   ├─ for each pair (in ThreadPoolExecutor, SCRAPER_CONCURRENCY cap):
   │   │
   │   ├─ SCRAPERS[site_name](url=site_config.build_search_url_for_keyword(keyword), limit=site_config.limit)
   │   │
   │   └─ scrape_site_for_keyword()
   │       ├─ search_jobs_via_api()                → list[Job], when the site has a usable `api` block
   │       │     └─ if not used or failed → _scrape_jobs_from_html()   (api_only sites fail instead)
   │       │           ├─ html_downloader.download_html(scraper.url)
   │       │           │     ├─ CurlCffiHtmlDownloader       (first attempt)
   │       │           │     ├─ CloudscraperHtmlDownloader   (second attempt)
   │       │           │     └─ PlaywrightHtmlDownloader     (last attempt, browser, ~280MB)
   │       │           │           each one runs only if the one before gave no usable page
   │       │           │           (non-200 status, challenge page or error)
   │       │           └─ scraper.parse(html)      → list[Job] (per-site selectors)
   │       ├─ _fill_missing_matched_keyword_and_posted_at() → stamp matched_keyword + parse posted_at
   │       ├─ _build_raw_payload()                 → every parsed job, all canonical fields
   │       ├─ _drop_stale_jobs()                   → drop jobs older than site.max_age_hours
   │       ├─ _drop_jobs_failing_content_filter()  → filter_reason() per job against site.filter
   │       ├─ _cap_jobs_to_limit()                 → keep the first site.limit jobs
   │       ├─ _fill_requirements_for_jobs()        → only when `requirements` is a saved field
   │       └─ _build_filtered_payload()            → project_jobs(fields), strip to configured fields
   │
   └─ return RunResult(exit_code, results)   results keyed by (keyword, site)
```

`scrape_all_sites` writes nothing to disk. Each pair gives a `FilteredAndRawPayloads(filtered, raw)`.
A pair that was skipped or crashed still gets an entry, with an `error` such as
`skipped: site has no entry in the job settings` or `crashed: RuntimeError`.
When the selection is invalid `scrape_all_sites` returns `exit_code=1` and no results. With
no keywords the error is `keywords are required`: keywords only come from the
caller, never from the job settings.

## Lifecycle of a Job dict

1. **Created** by `empty_job(site, title, company)` in the site's `parse()`.
   All canonical keys present, mostly `None`.
2. **Populated** by site-specific selectors / JSON walks in `parse()`.
3. **Enriched** by the runner: `matched_keyword`, `posted_at` (parsed UTC).
4. **Filtered** by max-age, then content filter, then capped to the site's `limit`.
5. **Projected** to the configured fields list — extra keys dropped.
6. **Returned** as one entry in the per-site payload `jobs` list.

Steps 3 and 4 happen on the in-memory dict before projection, so even
fields you didn't configure still drive the filter.

## Concurrency model

- One `ThreadPoolExecutor` per `runner.scrape_all_sites()` call, sized to `min(read_concurrency_from_env(), len(pairs))`. Concurrency comes from the `SCRAPER_CONCURRENCY` env var (default 2, valid 1 to 10, an invalid value logs a warning and uses 2). It is not a job setting.
- Each worker thread builds its own Playwright `sync_playwright()` context
  when needed — never share the instance across threads.
- The curl_cffi and cloudscraper downloaders keep no session between calls,
  so threads share none.
- Each worker returns its pair's payloads, and `scrape_all_sites` gathers them after the
  pool finishes, so threads share no output state.

## URL templating

Each site's `url_template` substitutes one of three placeholders before
fetching:

| Placeholder       | Format                          |
|-------------------|---------------------------------|
| `{keyword}`       | URL-encoded space               |
| `{keyword_slug}`  | lowercase + hyphens             |
| `{keyword_plus}`  | plus-separated                  |

Resolution happens in `SiteConfig.build_search_url_for_keyword(keyword)`. Validation runs at
config load time (`parse_job_settings_into_app_config()` formats with the placeholder keyword `data analyst` and rejects
unknown placeholders) so a bad template fails loudly on startup, not
mid-scrape.

## Site payload shape

This is the `filtered` payload for one `(keyword, site)` pair. `scrape_jobs`
stores it in Mongo as `filtered_results[*].payload`, and returns it in the
response when called with `include_payloads=true`.

```json
{
  "keyword": "software engineer",
  "fields": ["company", "location", "matched_keyword", "posted_at", "site", "title", "url"],
  "max_age_hours": 24,
  "filter": {"location": ["jakarta"]},
  "count": 2,
  "jobs": [
    {
      "site": "jobstreet",
      "matched_keyword": "software engineer",
      "title": "...",
      "company": "...",
      "url": "...",
      "location": "Jakarta Selatan",
      "posted_at": "2026-05-09T03:25:21+00:00"
    },
    ...
  ]
}
```

`fields` lists what was actually emitted (post-projection). `count` is
the post-filter, post-projection count. `jobs[*]` only contains keys that
were in `fields` (plus the always-on anchors). Every payload also has
`source` (`api` or `html`) and `fallback_reason`.

A failed pair has an `error` key instead of `jobs`, for example
`{"error": "fetch failed", "url": ..., "keyword": ..., "attempts": [...], "source": "html", "fallback_reason": null}`.
Each attempt is `{downloader, code, detail}`, see [`mcp.md`](mcp.md#scrape_jobs).

The `raw` payload (`raw_results[*].payload` in Mongo) has the same shape
without `max_age_hours` and `filter`, holds every parsed job before max-age,
filter and limit, and is `{"keyword", "count": 0, "jobs": [], "error"}` when
the pair failed.

## MCP layer relationship

`mcp_server/server.py` is a thin shell over `scraper.runner.scrape_all_sites` and
`scraper.job_settings.load_app_config`. It does no business logic of its own — every
tool delegates to the runner and job settings code. The UI server starts its runs
through this same `scrape_jobs` tool, with `save_run=False` and
`include_payloads=True`. So `scrape_jobs` does not save a UI run in `scrape_runs`
and its `mongo_id` is null. The UI server keeps the run in its own `ui_runs`
collection (see [`ui_runs` collection](#ui_runs-collection)).

`update_config` is the mutating tool. It validates
with the same parser (`config_loader.parse_job_settings_into_app_config`) before writing to Mongo.
See [`mcp.md`](mcp.md) for tool details.

## Where extension lives

| Want to add… | Touch |
|--------------|-------|
| A new site | `scraper/sites/<name>.py` + register in `sites/__init__.py::SCRAPERS`; add the `sites.<name>` entry to `seeds/job_settings.yaml` and to each environment with `update_config` |
| A new canonical field | `scraper/types.py` (Job + CANONICAL_FIELDS), per-site parsers fill it, optionally update `fields` |
| A new HTML downloader (e.g. proxy, undetected-chromedriver) | `scraper/html_downloaders/<name>.py`; export it in `html_downloaders/__init__.py`; insert into the `FallbackHtmlDownloader` list in `runner.scrape_all_sites()`, which runs `CurlCffiHtmlDownloader`, `CloudscraperHtmlDownloader`, `PlaywrightHtmlDownloader` in that order |
| A new MCP tool | `mcp_server/server.py`; mark with `@mcp.tool()` |
| A new filter key | `scraper/config_loader.py::FILTERABLE_FIELDS` + update Job extractors so the field is reliably populated |

The boundaries are explicit: site adapters know nothing about HTTP,
HTML downloaders know nothing about parsing, config knows nothing about runtime.
Keep that split.
