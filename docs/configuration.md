# Configuration reference

Job settings live in the `job_settings` Mongo collection, one document per
environment. Edit them at `/config`, or with the `update_config` MCP tool.
The proxy lives in the `PROXY_URL` env var and scrape concurrency in the
`SCRAPER_CONCURRENCY` env var. Results are never written to disk:
the runner returns them and `scrape_jobs` stores them in Mongo.

`scraper/config_loader.py::parse` validates all of them into an `AppConfig`
dataclass. A malformed value raises `ConfigError`. A save with a malformed value
changes nothing, and a run with one aborts.

This page documents every key the loader recognizes. For filter semantics
specifically, see [`filters.md`](filters.md).

## Top-level keys

The examples below show the keys as YAML, which is the format of
`seeds/job_settings.yaml`. All of them are job settings.

```yaml
default_fields: [...]
sites: {...}
```

| Key              | Required | Default        |
|------------------|----------|----------------|
| `default_fields` | no       | 4 fields       |
| `sites`          | yes      | none, non-empty |

Nothing else is allowed at the top level. `limit`, `max_age_hours` and
`filter` are per site only (see `sites` below): there are no global values and
no fallbacks. Concurrency is not a job setting; it comes from the
`SCRAPER_CONCURRENCY` env var (see "Concurrency" below). A save that sends
`limit`, `concurrency`, `max_age_hours` or `filter` at the top level is refused
with `not a job setting: <key>`.

### Keywords are not a job setting

The job settings hold no keywords. Every run names its own, and there is no
fallback:

- UI: the keyword box in "Start a run" (`POST /api/runs` needs `keywords`)
- MCP: the `keywords` argument of `scrape_jobs` (required, passed by name)
- CLI: `python -m scraper --keyword <kw> [--keyword <kw> ...] [sites...]`

Each keyword is run against every selected site, producing a
`(keyword, site)` cross-product. Each pair gets its own payload in the
`RunResult` that `scraper.runner.run` returns. Every keyword is trimmed and
blank ones are dropped, by `scraper.runner.normalize_keywords`, which the
runner, `scrape_jobs` and the CLI all use. A run with no keywords left is
refused with `keywords are required`: the runner returns exit code 1 without
fetching, `scrape_jobs` returns `ok: false` without saving, and the CLI prints
it to stderr and exits `2`. A save that sends `keywords` is refused with
`not a job setting: keywords`.

### `default_fields` (optional)

List of canonical field names to emit per Job. Default:
`[title, company, location, url]`. An empty list (`[]`) keeps only the
always-included anchors below.

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
- Per-site override: `sites.<name>.fields` replaces this list for that site.

```yaml
default_fields:
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
    fields: [...]
    api: {...}
```

| Key             | Required | When absent                         |
|-----------------|----------|-------------------------------------|
| `enabled`       | no       | `true`                              |
| `url_template`  | yes      | `ConfigError`                       |
| `limit`         | yes      | `ConfigError`                       |
| `max_age_hours` | no       | no age cut                          |
| `filter`        | no       | no filter                           |
| `fields`        | no       | `default_fields`                    |
| `api`           | no       | HTML only, from `url_template`      |

#### `sites.<name>.enabled`

Boolean. Disabled sites are skipped during default runs. CLI args
(`python -m scraper jobstreet`) override and run regardless of this flag.

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

#### `sites.<name>.fields`

Optional list of canonical field names. Replaces (does not merge into)
`default_fields` for this site only. Same validation as `default_fields`.

#### `sites.<name>.limit` (required)

Whole number from 1 to 200. Maximum number of jobs this site emits per
`(keyword, site)` pair, counted after the age cut and the filter. A site
without `limit` fails validation, and a save that sends `limit: null` is
refused.

#### `sites.<name>.max_age_hours`

Optional integer `>= 1`. Drops jobs whose parsed `posted_at` is older than
this many hours from now (UTC). Jobs with an unparseable `posted_date` are
kept (conservative). Absent or `null` means no age cut for this site.

Pair it with the URL templates' server-side recency params (e.g. jobstreet
`?daterange=1`, linkedin `&f_TPR=r86400`, indeed `&fromage=1`). See
[`sites.md`](sites.md) for the per-site param table. API sources also use it
as their search window.

#### `sites.<name>.filter`

Optional content filter applied after the age cut, before field projection.
Keys are `location`, `employment_type`, `work_type`. Each value can be a
single string or a list. Substring + case-insensitive. Absent, `{}` or only
empty lists means no filter for this site. See [`filters.md`](filters.md).

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
      locations: [Jakarta Raya, Bandung Jawa Barat]
      country_wide: true            # optional
      delay_seconds: [4, 6]         # optional, default [1, 2]
```

- `enabled` (default `true`): `false` skips the API and uses HTML only.
- `locations`: one API call per entry. Format is per site: JobStreet `where`
  label, Glints location UUID, LinkedIn place name (`"Jakarta, Indonesia"`).
- The UI Config page picks `locations` from the fixed list in
  `scraper/api/locations.py` (JobStreet, Glints, LinkedIn). To add a city,
  add one `("Label", "value")` line to that site's tuple (same label order on
  every site). LinkedIn has only 6 verified cities because rate limits blocked
  checking the rest.
- `country_wide`: adds one extra call without a city and keeps only jobs whose
  location is labelled just `Indonesia`.
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
| top-level keys            | Only `default_fields`, `sites`                   | `ConfigError` (`not a job setting`) |
| `sites`                   | Non-empty mapping                                | `ConfigError`     |
| `sites.<name>.limit`      | Required, whole number from 1 to 200             | `ConfigError`     |
| `sites.<name>.max_age_hours` | Integer >= 1 or null                          | `ConfigError`     |
| `sites.<name>.url_template` | Non-empty string with valid placeholders only  | `ConfigError`     |
| `default_fields` entries  | Strings; unknown names → warning, dropped on load, refused on save | `[config] warning` (load continues) |
| `sites.<name>.filter` keys | One of `location`, `employment_type`, `work_type`; unknown → warning, dropped | `[config] warning` |
| `sites.<name>.filter` values | String or list-of-strings                        | `ConfigError`     |

## Concurrency

`SCRAPER_CONCURRENCY` (env var) is how many `(keyword, site)` pairs run at once
through a thread pool. Default `2`, valid `1` to `10`. A value that is not a
whole number in that range logs a warning and uses `2`. `1` runs pairs one by
one without a thread pool. Each Playwright fallback uses ~250-300MB RAM, so
tune it for the memory you have. It is read at the start of every run, in
`scraper/config_loader.py::resolve_concurrency`, and passed through to the
`scraper-mcp` and `scraper-ui` containers by `docker-compose.yml`. Change it in
`.env` and recreate the containers.

## Migration from global values

Older settings documents had global `limit`, `concurrency`, `max_age_hours`,
`filter` and `keywords`. The first time `JobSettingsStore.read` sees such a
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

The result is validated before anything is written. When it is still not
valid (for example a bad `url_template`), nothing is written, the original
document stays as it was, and the read fails with `The stored job settings
could not be migrated and were left unchanged: <problem>`. Fix the document by
hand and read again.

Before the migrated document is written, the original document is copied once
to `_id: "active_pre_migration_backup"` in the same `job_settings` collection.
A later migration never replaces that copy. Reads, saves and seeding only touch
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

config.default_fields
config.sites
config.fields_for("glints")

site = config.site("glints")
site.limit
site.max_age_hours
site.filter
```

| Expression                    | Type                       |
|-------------------------------|----------------------------|
| `config.default_fields`       | `tuple[str, ...]`          |
| `config.sites`                | `tuple[SiteConfig, ...]`   |
| `config.fields_for(name)`     | `frozenset[str]`           |
| `config.site(name)`           | `SiteConfig \| None`       |
| `site.limit`                  | `int`                      |
| `site.max_age_hours`          | `int \| None`              |
| `site.filter`                 | `dict[str, list[str]]`, `{}` = no filter |

Concurrency is not on the config: `resolve_concurrency()` reads it from the
env var.

## Live editing via MCP

The `/config` page is the normal way to change job settings. The MCP server
also exposes `update_config`. See [`mcp.md`](mcp.md) for the tool catalog and
patch shape.

Every save is validated through this same loader first. An invalid patch
returns an error and changes nothing.
