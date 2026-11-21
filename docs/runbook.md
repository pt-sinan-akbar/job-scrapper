# Runbook — common config edits

How to translate user requests into `update_config` patches. Each recipe
shows the exact tool call so you can copy-paste-modify.

The general loop is always:

1. `get_config` → see current shape
2. Compose a minimal patch
3. `update_config` with that patch and the version from `get_config`
4. On `ok=false`, surface the `message` verbatim

For schema details see [`configuration.md`](configuration.md).
For the tool catalog see [`mcp.md`](mcp.md).

## "Search for a different role"

User: "switch the search to data analyst" / "add backend developer to the keywords"

Keywords are not a job setting, so there is nothing to patch. Pass them to
`scrape_jobs` on every call:

```json
{"keywords": ["software engineer", "backend developer"]}
```

`keywords` is required. A call with `null` or `[]` runs nothing and returns
`ok: false` with the error reason `keywords are required`. An `update_config`
patch with `keywords` is refused with `not a job setting: keywords`.

## "Only show jobs from last X hours"

User: "tighten to last 6 hours" / "show me last week's jobs"

`max_age_hours` is per site. There is no global value, so patch every site the
user means (all enabled sites when they say "everything"):

```json
{"patch": {"sites": {
  "jobstreet": {"max_age_hours": 6},
  "glints":    {"max_age_hours": 6},
  "linkedin":  {"max_age_hours": 6},
  "indeed":    {"max_age_hours": 6},
  "upwork":    {"max_age_hours": 6}
}}}
```

`null` turns a site's age cut off. Pair with URL params if you also want server-side filtering. See
[`sites.md`](sites.md) for the param table per site. Example for last
week (jobstreet + linkedin):

```json
{"patch": {
  "sites": {
    "jobstreet": {"max_age_hours": 168, "url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=7"},
    "linkedin":  {"max_age_hours": 168, "url_template": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword}&location=Indonesia&f_TPR=r604800&start=0"}
  }
}}
```

## "Disable / re-enable a site"

User: "stop scraping LinkedIn" or "Glints is being noisy, turn it off"

```json
{"patch": {"sites": {"linkedin": {"enabled": false}}}}
```

To re-enable:

```json
{"patch": {"sites": {"linkedin": {"enabled": true}}}}
```

## "Filter jobs to a specific location"

User: "only Jakarta" / "Jakarta or Bandung please"

Each site has its own `filter`, replaced whole. Patch every site the user
means, and keep that site's other filter keys:

```json
{"patch": {"sites": {
  "jobstreet": {"filter": {"location": ["jakarta", "bandung"]}},
  "glints":    {"filter": {"location": ["jakarta", "bandung"]}},
  "linkedin":  {"filter": {"location": ["jakarta", "bandung"]}},
  "indeed":    {"filter": {"location": ["jakarta", "bandung"]}}
}}}
```

Leave `upwork` out: its jobs are remote and worldwide. The location filter resolves region names — `jakarta` catches Jakarta Barat, Jakarta
Selatan, Area DKI Jakarta, etc. See [`filters.md`](filters.md) for full
filter semantics.

## "Only internships" or "no internships"

User: "internships only" / "exclude internships, full-time only"

Internships only:
```json
{"patch": {"sites": {"glints": {"filter": {"location": ["jakarta"], "employment_type": "internship"}}}}}
```

Full-time only:
```json
{"patch": {"sites": {"glints": {"filter": {"location": ["jakarta"], "employment_type": "full-time"}}}}}
```

Note: `employment_type` is reliably populated only by Glints. Other sites
emit null and pass via the conservative null-rule. The filter mainly
narrows Glints' output.

## "Remote-friendly only"

User: "remote work only" / "remote or hybrid is fine"

```json
{"patch": {"sites": {"glints": {"filter": {"work_type": ["remote", "hybrid"]}}}}}
```

Same coverage caveat as `employment_type` — Glints reliably emits
`work_type`, others don't.

## "Increase / decrease how many jobs per site"

User: "give me 10 per site instead of 2" / "lower to 1, this is too noisy"

`limit` is per site and required on every site (1 to 200). Patch each site the
user means:

```json
{"patch": {"sites": {
  "jobstreet": {"limit": 10},
  "glints":    {"limit": 10},
  "linkedin":  {"limit": 10},
  "indeed":    {"limit": 10}
}}}
```

`limit: null` is refused. Higher `limit` increases scrape time and block risk.
Tighten that site's `max_age_hours` or filter at the same time to keep output
relevant.

## "Speed it up" / "slow it down"

User: "scrape faster" or "running too hot, slow it down"

Not a job setting, so `update_config` cannot change it (a `concurrency` patch
is refused). Concurrency is the `SCRAPER_CONCURRENCY` env var: how many
`(keyword, site)` pairs run at once. Default 2, valid 1 to 10; an invalid value
logs a warning and uses 2. In prod it is the `SCRAPER_CONCURRENCY` GitHub
variable, applied on the next deploy (see [`deploy.md`](deploy.md)). Locally,
set it in `.env` and recreate the containers:

```bash
SCRAPER_CONCURRENCY=4
docker compose up -d scraper-mcp scraper-ui
```

Each Playwright fallback consumes ~250-300MB RAM. On a 2GB host, stay at
2; on a bigger host, 4 is safe.

## "Reset the filter"

User: "drop the filter, show everything"

Send `{}` for each site whose filter should go:

```json
{"patch": {"sites": {"jobstreet": {"filter": {}}, "glints": {"filter": {}}}}}
```

To clear a single key, send that site's remaining keys without the one to
drop:

```json
{"patch": {"sites": {"glints": {"filter": {"location": ["jakarta"]}}}}}
```

(Removes `employment_type` and `work_type` from Glints if they were set.)

## "Change one site's filter"

User: "Glints should only show internships"

```json
{"patch": {"sites": {"glints": {"filter": {"employment_type": "internship"}}}}}
```

The site's whole `filter` is replaced, and no other site changes. There is no
global filter to fall back to: `filter: {}` means no filter for that site.

## "Add new fields to the output"

User: "include posted_at and salary in the JSON"

```json
{"patch": {"fields": ["title", "company", "location", "url", "salary", "posted_date", "posted_at"]}}
```

`fields` is one list for every site. There is no per-site list: a patch with
`sites.<name>.fields` is refused.

`site`, `matched_keyword`, `title`, `company`, `url` are anchors and always
appear regardless of this list.

## "Run an ad-hoc scrape without saving config"

User: "just run it once for 'fullstack engineer'" — no config persist

Skip `update_config` entirely; use `scrape_jobs` with explicit args:

```json
{"keywords": ["fullstack engineer"], "sites": ["linkedin", "jobstreet"]}
```

The saved job settings are unchanged. Add `"save_run": false` to keep the run
out of MongoDB as well.

## "Show me the current settings"

```json
// no patch needed
"call_tool": "get_config"
```

For a higher-level view (resolved sample URLs, enabled list):

```json
"call_tool": "list_sites"
```

## When validation fails

`update_config` returns `{ok: false, reason: "<kind>", message: "<text>"}`. `reason` is `invalid`, `conflict`, or `unavailable`. Common `message` values for `invalid`:

| Error fragment                                    | Cause                                              |
|---------------------------------------------------|----------------------------------------------------|
| `sites.<name>.limit is required`                  | Site has no `limit`, or the patch sent `limit: null` |
| `sites.<name>.limit must be a whole number from 1 to 200` | Sent `0`, over 200, or a non-integer       |
| `not a job setting: proxy`                        | Sent `proxy` or another key that is not a job setting |
| `not a job setting: limit` (or `concurrency`, `max_age_hours`, `filter`) | Sent a global value; put it on each site instead, concurrency is `SCRAPER_CONCURRENCY` |
| `not a job setting: keywords`                     | Keywords are not stored; pass them to `scrape_jobs` instead |
| `sites.<name>.max_age_hours must be >= 1`         | Sent `0` or negative                               |
| `url_template uses unknown placeholder ...`       | URL has `{x}` not in `keyword/keyword_slug/keyword_plus` |
| `sites.<name>.filter.<key> must be a string or list` | Sent a number, dict, or other non-string value     |

When a read fails with `The stored job settings could not be migrated and were
left unchanged: <problem>`, an old document still has global values and the
migrated result would not be valid. Nothing was written. Fix `<problem>` in the
`active` document by hand, then read again.

When you see these, don't loop blindly. Surface the verbatim `message` to the
user and ask how to proceed (or whether to drop the offending key).

## Restore settings from before the migration

The global value migration is one-way: older images cannot read the migrated
document. The original is kept once as `_id: "active_pre_migration_backup"`
in `job_settings`. A later migration (such as `default_fields` to `fields`)
never replaces it, so the backup can be older than the last migration. Stop the scraper containers, then in `mongosh`:

```js
use job_scraper
const backup = db.job_settings.findOne({ _id: "active_pre_migration_backup" })
db.job_settings.replaceOne(
  { _id: "active" },
  { version: backup.version, settings: backup.settings,
    updated_at: backup.updated_at, updated_by: backup.updated_by }
)
```

Start the old image after that. Changes saved after the migration are lost.
See [`deploy.md`](deploy.md#job-settings-migration-is-one-way).
