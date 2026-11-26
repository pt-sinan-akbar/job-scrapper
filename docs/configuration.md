# Configuration reference

Job settings live in the `job_settings` Mongo collection, one document per
environment. Edit them at `/config`, or with the `update_config` MCP tool.
The proxy lives in the `PROXY_URL` env var and scrape concurrency in the
`SCRAPER_CONCURRENCY` env var. Results are never written to disk:
the runner returns them and `scrape_jobs` stores them in Mongo.

`scraper/config_loader.py::parse_job_settings_into_app_config` validates all of them into an `AppConfig`
dataclass. A malformed value raises `ConfigError`. A save with a malformed value
changes nothing, and a run with one aborts.

This page documents every key the loader recognizes. For filter semantics
specifically, see [`filters.md`](filters.md).

## Top-level keys

The examples below show the keys as YAML, which is the format of
`seeds/job_settings.yaml`. All of them are job settings.

```yaml
fields: [...]
sites: {...}
```

| Key      | Required | Default         |
|----------|----------|-----------------|
| `fields` | no       | 4 fields        |
| `sites`  | yes      | none, non-empty |

Nothing else is allowed at the top level. `limit`, `max_age_hours` and
`filter` are per site only (see `sites` below): there are no global values and
no fallbacks. Concurrency is not a job setting; it comes from the
`SCRAPER_CONCURRENCY` env var (see "Concurrency" below). A save that sends
`limit`, `concurrency`, `max_age_hours` or `filter` at the top level is refused
with `not a job setting: <key>`.

### Keywords are not a job setting

The job settings hold no keywords. Every run names its own, and there is no
fallback:

- UI: the keyword box in "Start a run" (`POST /api/scrapes` needs `keywords`)
- MCP: the `keywords` argument of `scrape_jobs` (required, passed by name)

Each keyword is run against every selected site, producing a
`(keyword, site)` cross-product. Each pair gets its own payload in the
`RunResult` that `scraper.runner.scrape_all_sites` returns. Every keyword is trimmed and
blank ones are dropped, by `scraper.runner.strip_and_drop_blank_keywords`, which the
runner and `scrape_jobs` both use. The UI starts its runs through `scrape_jobs`. A run with no keywords left is
refused with `keywords are required`: the runner returns exit code 1 without
fetching, and `scrape_jobs` returns `ok: false` without saving. A save that sends `keywords` is refused with
`not a job setting: keywords`.

### `fields` (optional)

One list of canonical field names to emit per Job, used for every site. Default:
`[title, company, location, url]`. An empty list (`[]`) keeps only the
always-included anchors below. A list whose names are all unknown falls back
to the default.

Allowed canonical fields:

```
site                matched_keyword     title             company
url                 location            salary            posted_date
posted_at           work_type           employment_type   experience_level
job_id              requirements
```

- `site`, `matched_keyword`, `title`, `company`, `url` are **always
  included** regardless of this list (anchors).
- Unknown field names log a warning and are silently dropped when settings
  load — they don't abort the load. Saving through `update_config` (and the
  UI) refuses them instead, so new unknown names never get stored.
- There is no per-site list. A `fields` key inside a site is refused with
  `sites.<name>.fields is no longer supported, use the top-level fields`.

```yaml
fields:
  - title
  - company
  - location
  - url
  - salary
  - posted_date
  - posted_at
```

### `sites` (required)

Mapping from site-name → site config. Site name must match a registered
scraper in `scraper/sites/__init__.py::SCRAPERS`. Currently supported:

- `jobstreet`
- `glints`
- `linkedin`
- `indeed`
- `upwork`

Each site entry:

```yaml
sites:
  <name>:
    enabled: true
    url_template: "https://...?{keyword}..."
    limit: 10
    max_age_hours: 72
    filter: {...}
    api: {...}
```

| Key             | Required | When absent                         |
|-----------------|----------|-------------------------------------|
| `enabled`       | no       | `true`                              |
| `url_template`  | yes      | `ConfigError`                       |
| `limit`         | yes      | `ConfigError`                       |
| `max_age_hours` | no       | no age cut                          |
| `filter`        | no       | no filter                           |
| `api`           | no       | HTML only, from `url_template`      |

#### `sites.<name>.enabled`

Boolean. Disabled sites are skipped during default runs. Sites named in the
`sites` argument of `scrape_jobs` override and run regardless of this flag.

#### `sites.<name>.url_template`

String. The URL fetched per `(keyword, site)` pair. Three placeholders are
substituted:

| Placeholder       | Format                          | Example for `software engineer` |
|-------------------|---------------------------------|---------------------------------|
| `{keyword}`       | URL-encoded space (`%20`)       | `software%20engineer`           |
| `{keyword_slug}`  | lowercase + hyphens             | `software-engineer`             |
| `{keyword_plus}`  | plus-separated                  | `software+engineer`             |

Pick the one that matches the site's URL convention. The loader validates
all placeholders against this allowlist by formatting each template with the
placeholder keyword `data analyst`; unknown placeholder → `ConfigError`.

```yaml
sites:
  jobstreet:
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs?daterange=1"
  indeed:
    url_template: "https://id.indeed.com/jobs?q={keyword_plus}&l=Indonesia&fromage=1"
```

#### `sites.<name>.limit` (required)

Whole number from 1 to 200. Maximum number of jobs this site emits per
`(keyword, site)` pair, counted after the age cut and the filter. A site
without `limit` fails validation, and a save that sends `limit: null` is
refused.

#### `sites.<name>.max_age_hours`

Optional integer `>= 1`. Drops jobs whose parsed `posted_at` is before
midnight UTC of today minus this many hours rounded up to whole days (72 means
from midnight UTC three days ago, 36 means two days ago). Jobs with an
unparseable `posted_date` are kept (conservative). Absent or `null` means no
age cut for this site. A scrape can replace it for one call with
`max_age_hours` (72, 168 or 720), see [`mcp.md`](mcp.md#scrape_jobs).

Pair it with the URL templates' server-side recency params (e.g. jobstreet
`?daterange=1`, linkedin `&f_TPR=r86400`, indeed `&fromage=1`). See
[`sites.md`](sites.md) for the per-site param table. API sources also use it
as their search window.

#### `sites.<name>.filter`

Optional content filter applied after the age cut, before field projection.
Keys are `location`, `employment_type`, `work_type`. Each value can be a
single string or a list. Substring + case-insensitive, except `location`,
which resolves names through the region index. Absent, `{}` or only
empty lists means no filter for this site. See [`filters.md`](filters.md).

`location` accepts only six values, in any letter case: `Jakarta`,
`Tangerang`, `Tangerang Selatan`, `Bandung`, `Bekasi` and `Indonesia`
(all regions). A save with any other value is refused. A stored value that
is not in the list is dropped with a warning when the settings are read.
The same list decides which locations the site is searched for (see
[`sites.<name>.api`](#sitesnameapi)).

```yaml
sites:
  jobstreet:
    filter:
      location: [jakarta, bandung]
      employment_type: [full-time, internship]
      work_type: [remote, hybrid]
```

### `sites.<name>.api`

Optional block that makes a site fetch from its JSON/API source first.
Omit it (e.g. `indeed`) and the site uses `url_template` only.

```yaml
sites:
  jobstreet:
    api:
      enabled: true                 # optional, default true
      delay_seconds: [4, 6]         # optional, default [1, 2]
```

- `enabled` (default `true`): `false` skips the API and uses HTML only.
- The searched locations come from the site's `filter.location`, not from
  this block. Each picked city becomes one API call with that site's own
  search value, read from `scraper/api/location_mapping.yaml` (JobStreet
  `where` label, Glints location UUID, LinkedIn place name, Indeed `where`
  text). Cities that share a value on a site are sent once: on LinkedIn,
  Jakarta, Tangerang, Tangerang Selatan and Bekasi are all
  `"Jakarta, Indonesia"`.
- `Indonesia` in `filter.location` adds one country-wide call, and every job
  it returns is kept. An empty `filter.location` acts like `Indonesia` alone.
- A site with no entry in the mapping file (Upwork) always makes one call
  with no location.
- When no picked city has a search value for the site and `Indonesia` is not
  picked, the API is skipped and the site uses `url_template` (HTML).
- Indeed has no `api` block but follows the same plan inside
  `IndeedScraper.parse`: one GraphQL call per city value within 5 miles, plus
  one for `Indonesia` when picked.
- Old stored `api.locations` and `api.country_wide` keys are ignored.
- To add a city, add it to `city_locations` and to every site under `sites`
  in `scraper/api/location_mapping.yaml`. The file ships with the code and is
  read once per process.
- `delay_seconds` (default `[1, 2]`): random pause between this site's API
  calls, as `[min, max]` seconds. LinkedIn uses `[4, 6]` because its guest
  endpoint returns `429` after a few quick calls.
- Results from all calls are de-duplicated by `job_id`, then by URL.
- Fallback: any API failure (HTTP error, non-JSON, GraphQL error, network
  error) reruns that whole site + keyword through `url_template` (HTML). An
  empty API result is valid and does not trigger the fallback.
- `limit` still means "max jobs after filters"; each API call pages up to it.

## Validation rules summary

The loader (`parse`) enforces:

| Key                       | Rule                                             | On failure        |
|---------------------------|--------------------------------------------------|-------------------|
| top-level keys            | Only `fields`, `sites`                           | `ConfigError` (`not a job setting`) |
| `sites`                   | Non-empty mapping                                | `ConfigError`     |
| `sites.<name>.limit`      | Required, whole number from 1 to 200             | `ConfigError`     |
| `sites.<name>.max_age_hours` | Integer >= 1 or null                          | `ConfigError`     |
| `sites.<name>.url_template` | Non-empty string with valid placeholders only  | `ConfigError`     |
| `fields` entries          | Strings; unknown names → warning, dropped on load, refused on save | `[config] warning` (load continues) |
| `sites.<name>.fields`     | Not allowed                                      | `ConfigError` (`no longer supported`) |
| `sites.<name>.filter` keys | One of `location`, `employment_type`, `work_type`; unknown → warning, dropped | `[config] warning` |
| `sites.<name>.filter` values | String or list-of-strings                        | `ConfigError`     |
| `sites.<name>.filter.location` values | One of the six location options, any letter case; unknown → warning, dropped on load, refused on save | `[config] warning` on load, `ConfigError` on save |

## Concurrency

`SCRAPER_CONCURRENCY` (env var) is how many `(keyword, site)` pairs run at once
through a thread pool. Default `2`, valid `1` to `10`. A value that is not a
whole number in that range logs a warning and uses `2`. `1` runs pairs one by
one without a thread pool. Each Playwright fallback uses ~250-300MB RAM, so
tune it for the memory you have. It is read at the start of every run, in
`scraper/config_loader.py::read_concurrency_from_env`, and passed through to the
`scraper` service by `infra/compose/docker-compose.yml`. Change it in
`.env` and recreate the container.

## Migration from global values

Older settings documents had global `limit`, `concurrency`, `max_age_hours`,
`filter` and `keywords`, a top-level `default_fields`, or per-site `fields`
overrides. The first time `JobSettingsStore.read` sees such a
document it migrates it, once, in one pass, and stores the result:

- a site without a usable `limit` (missing, `null` or not a whole number) gets
  the global `limit`, or `2` when there was no usable one. The sites that got
  `2` are named in one WARNING line
- every site `limit` is clamped to 1..200
- a site without `max_age_hours` gets the global one, when it was set and valid
- a site with no `filter` key gets the global filter, when it was a non-empty
  mapping; a site that already had a `filter` (even `{}`) keeps it
- the four global keys are deleted (`concurrency` is dropped; use
  `SCRAPER_CONCURRENCY`)
- `keywords` is deleted and not copied anywhere; callers pass keywords on
  every run. A document that only has `keywords` still gets the `limit` fill
  and clamp above, so it always ends valid
- a top-level `default_fields` is renamed to `fields`. When the document
  already has `fields`, that value is kept and `default_fields` is dropped
- every `sites.<name>.fields` override is dropped, and the sites that lost one
  are named in one WARNING line. The top-level `fields` applies to every site

The result is validated before anything is written. When it is still not
valid (for example a bad `url_template`), nothing is written, the original
document stays as it was, and the read fails with `The stored job settings
could not be migrated and were left unchanged: <problem>`. Fix the document by
hand and read again.

Before the migrated document is written, the original document is copied once
to `_id: "active_pre_migration_backup"` in the same `job_settings` collection.
A later migration never replaces that copy, so when an earlier migration
already made a backup, the `default_fields` rename does not make a new one:
the backup stays the document from before that first migration. Reads, saves
and seeding only touch
`_id: "active"`, so the backup never changes them. See
[`deploy.md`](deploy.md#job-settings-migration-is-one-way) for how to restore it.

The migrated document is saved with the next version and `updated_by:
"migration"`, and one INFO line is logged. The write only lands if the version
has not changed, so two processes migrating at once store it once; the loser
re-reads the stored result. Every read and save goes through it, so the UI
always gets the migrated version. A page opened before the migration gets a
conflict on save and must reload.

## Proxy configuration

Route HTTP requests through a proxy server. Useful for bypassing datacenter IP blocks by using residential IPs.

```bash
PROXY_URL="socks5://localhost:1080"
```

The var must be set. When it is not, `scrape_jobs` returns `ok: false` and says so. Set it to empty for a direct connection. This stops a missing prod var from turning the proxy off without anyone noticing.

### Supported proxy formats

| Format | Example | Use case |
|--------|---------|----------|
| SOCKS5 | `socks5://localhost:1080` | SSH tunnels, residential proxies |
| HTTP | `http://proxy.example.com:8080` | Corporate proxies |
| HTTPS | `https://proxy.example.com:8080` | Secure corporate proxies |
| Auth | `socks5://user:pass@host:1080` | Authenticated proxies |

### Common setup: SSH tunnel

On VPS (remote server), create SOCKS5 tunnel to your home machine:

```bash
# From VPS, connect to your home machine
ssh -D 1080 -f -N user@your-home-ip

# Test proxy works
curl --socks5 localhost:1080 http://httpbin.org/ip
# Should show your home IP, not VPS IP
```

Then set the env var:
```bash
PROXY_URL="socks5://localhost:1080"
```

### Docker considerations

When using `--network host` mode (required for localhost proxy):
- Container shares host network stack
- `localhost:1080` inside container = `localhost:1080` on VPS host
- No port mapping needed

## Loading the resolved config

```python
from scraper.job_settings import load_app_config, open_store

config = load_app_config(open_store())

config.fields
config.sites
config.list_saved_fields()

site = config.find_site_config("glints")
site.limit
site.max_age_hours
site.filter
```

| Expression                               | Type                       |
|------------------------------------------|----------------------------|
| `config.fields`                          | `tuple[str, ...]`          |
| `config.sites`                           | `tuple[SiteConfig, ...]`   |
| `config.list_saved_fields()`             | `frozenset[str]`, `fields` plus the anchors |
| `config.find_site_config(site_name)`     | `SiteConfig \| None`       |
| `site.limit`                             | `int`                      |
| `site.max_age_hours`                     | `int \| None`              |
| `site.filter`                            | `dict[str, list[str]]`, `{}` = no filter |

Concurrency is not on the config: `read_concurrency_from_env()` reads it from the
env var.

## Live editing via MCP

The `/config` page is the normal way to change job settings. The MCP server
also exposes `update_config`. See [`mcp.md`](mcp.md) for the tool catalog and
patch shape.

Every save is validated through this same loader first. An invalid patch
returns an error and changes nothing.
