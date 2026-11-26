# Filter options

Each site's `filter` (`sites.<name>.filter`) drops that site's jobs from the
output. It runs after the site's recency cut (`sites.<name>.max_age_hours`)
and before fields are projected for output. There is no global filter: a site
without a `filter` key, with `filter: {}`, or with only empty lists has no
filter.

> **Ordering:** for `linkedin`, `glints`, and `jobstreet`, both `filter:` and
> `max_age_hours` run **before** the per-site `limit` cap, so `limit` means "up
> to N jobs *after* filtering" — you reliably get up to N matches, not the first
> N parsed (which were often filtered down to zero). With no filter set,
> behavior is unchanged (still the first N). `indeed` works the same way: it
> returns every job of its location searches and the runner cuts to `limit`
> after filtering.

## Quick reference

```yaml
sites:
  jobstreet:
    filter:
      location: [jakarta, bandung]
      employment_type: [full-time, internship]
      work_type: [remote, hybrid]
```

## Matching semantics

- **Substring** match, **case-insensitive**, against the job's canonical field
  value, for every key but `location`.
- **`location`** resolves names through the region index (see
  [Region index](#region-index)). `jakarta` matches `Jakarta`, `Jakarta Barat`,
  `Area DKI Jakarta`.
- **Within a key**: list-of-values is OR. `location: [jakarta, bandung]` keeps
  any job where `location` matches `jakarta` OR `bandung`.
- **Across keys**: AND. Every declared key must match at least one of its
  candidate values for the job to survive.
- **Null fields are kept (conservative)**. If a site couldn't extract a field,
  the job is not penalized. Only an explicit non-matching value drops the job.
- **Single string** is shorthand for a 1-item list. `work_type: remote` is
  equivalent to `work_type: [remote]`.

## Per-key reference

### `location`

The filter accepts only six values, in any letter case: `Jakarta`,
`Tangerang`, `Tangerang Selatan`, `Bandung`, `Bekasi` and `Indonesia`. A save
with any other value is refused. The same list decides which locations each
site is searched for (see [`configuration.md`](configuration.md#sitesnameapi)).

`Indonesia` means all regions: a job is kept when its location resolves to any
Indonesian region, when one part of its location is literally `Indonesia`, or
when its location is blank. Foreign or unknown places such as `Bangkok` or
`Remote` are dropped.

The job's own location is free-form: whatever the source emits. The
comparison goes through the region index below.

Examples of job locations observed across platforms (sample, not exhaustive):

```
jakarta              jakarta selatan        jakarta barat
jakarta timur        area dki jakarta       bandung
surabaya             semarang               bekasi
tangerang            batam                  bali
buleleng             cikarang               cilandak
indonesia            remote
```

Tip: one region name catches multiple variants.
`location: jakarta` catches `Jakarta`, `Jakarta Barat`, `Jakarta Selatan`,
`Area DKI Jakarta`, etc. in one go.

#### Region index

The location filter resolves names through the Indonesian region list in the
Mongo `wilayah` collection (provinces, cities and districts). A job is kept
when its location resolves to a region under one of the filter's regions, and
dropped when it resolves somewhere else, unless `indonesia` is picked: then a
location that resolves to any region is kept. When the location resolves to no
region, the job is kept only if a filter term that is not a region name (such
as `indonesia`) equals one part of the location.

- **Loaded on first use.** The list is read the first time a location filter
  needs it. A run with no location filter never reads `wilayah`.
- **Cached for the process.** After a successful load the copy stays in memory
  until the process stops. The MCP and UI processes each hold their own
  copy, so restart the `job-scraper` container after reseeding `wilayah` (see
  [`deploy.md`](deploy.md#restart-after-reseeding)).
- **Retried after a failed load.** If Mongo is unreachable or `wilayah` is
  empty, the filter falls back to plain substring matching and logs a warning.
  The load is tried again after 60 s, not on every job.

### `employment_type`

Lowercase, hyphenated canonical set. Glints values are normalized at extraction
time (`FULL_TIME` → `full-time`).

Allowed values:

| Value         | Meaning                                       |
|---------------|-----------------------------------------------|
| `full-time`   | Permanent full-time position                  |
| `part-time`   | Permanent part-time position                  |
| `contract`    | Fixed-term contractor / consultant            |
| `internship`  | Student or entry-level internship             |
| `freelance`   | Project-based / gig                           |

Coverage today: **Glints** reliably emits this field. Jobstreet, LinkedIn, and
Indeed currently emit `null` for this field and pass through the filter via the
null-rule. If you need strict matching across all sites, expect this filter to
have impact only on Glints' jobs for now.

### `work_type`

Lowercase canonical set.

Allowed values:

| Value     | Meaning                                                     |
|-----------|-------------------------------------------------------------|
| `onsite`  | Employee works fully on company premises                    |
| `remote`  | Employee works fully remotely                               |
| `hybrid`  | Mix of onsite and remote (split varies per company)         |

Coverage today: **Glints** emits all three. Other sites currently emit `null`
and pass via the null-rule.

## One filter per site

Each site has its own filter and nothing is shared or merged between sites.
To use the same filter on several sites, set it on each one. The seed gives
`jobstreet`, `glints`, `linkedin` and `indeed` the same Indonesian city list
and leaves `upwork` with `filter: {}`, because all Upwork jobs are remote.

```yaml
sites:
  glints:
    filter:
      employment_type: full-time
  upwork:
    filter: {}
```

Here Glints keeps only full-time jobs and Upwork has no filter. Older settings
documents with a global `filter` are migrated on first read: the global filter
is copied into every site that had no `filter` key (see
[`configuration.md`](configuration.md#migration-from-global-values)).

## Reading the runtime log

For each site, the runner logs one line with how many jobs survived the
recency cut and the filter together, split by why the others were dropped.
Logs go to stdout only, so read them with `docker logs job-scraper` (MCP
calls and runs started from the UI):

```
[jobstreet:software-engineer] max_age=24h cutoff=2026-11-21T00:00:00+00:00 filter={'location': ['jakarta', 'bandung']} kept 1/5 (dropped 1 stale, 3 filter)
```

At debug level each dropped job also gets its own line with the exact reason:

```
[jobstreet:software-engineer] drop stale: 'Data Analyst' posted_at=2026-11-19T10:00:00+00:00 < cutoff=2026-11-21T00:00:00+00:00
[jobstreet:software-engineer] drop filter: 'Backend Engineer' location='Surabaya' resolved out of scope, not in ['jakarta', 'bandung']
```

Each site payload (`results[*].payload` in the `scrape_jobs` response and in Mongo) also records the filter that was applied:

```json
{
  "keyword": "software engineer",
  "max_age_hours": 24,
  "filter": {
    "location": ["jakarta", "bandung"],
    "employment_type": ["full-time", "internship"]
  },
  "count": 1,
  "jobs": [...]
}
```

## Common recipes

Each recipe is the `filter` block of one site, `sites.<name>.filter`.

### Jakarta + nearby cities, full-time only

```yaml
filter:
  location: [jakarta, bekasi, tangerang, tangerang selatan]
  employment_type: full-time
```

### Internships anywhere remote-friendly

```yaml
filter:
  employment_type: internship
  work_type: [remote, hybrid]
```

### Strict remote-only (Glints will dominate this)

```yaml
filter:
  work_type: remote
```

### Loosen further when filters return zero

If a combination yields empty output across all sites, drop the most
restrictive key first — typically `work_type` or `employment_type`. The
runtime log shows `kept N/M (dropped X stale, Y filter)` per site so you can tell which
filter is doing the cutting.
