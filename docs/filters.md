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
> behavior is unchanged (still the first N). `indeed` caps at the API and is
> unaffected.

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
  value. `jakarta` matches `Jakarta`, `Jakarta Barat`, `Area DKI Jakarta`.
- **Within a key**: list-of-values is OR. `location: [jakarta, bandung]` keeps
  any job where `location` substring-matches `jakarta` OR `bandung`.
- **Across keys**: AND. Every declared key must match at least one of its
  candidate values for the job to survive.
- **Null fields are kept (conservative)**. If a site couldn't extract a field,
  the job is not penalized. Only an explicit non-matching value drops the job.
- **Single string** is shorthand for a 1-item list. `work_type: remote` is
  equivalent to `work_type: [remote]`.

## Per-key reference

### `location`

Free-form. There is no fixed enum — the value is whatever the source page
emits, normalized only by stripping/lowercasing for the comparison.

Examples observed across platforms (sample, not exhaustive):

```
jakarta              jakarta selatan        jakarta barat
jakarta timur        area dki jakarta       bandung
surabaya             semarang               bekasi
tangerang            batam                  bali
buleleng             cikarang               cilandak
indonesia            remote
```

Tip: a short substring catches multiple variants.
`location: jakarta` catches `Jakarta`, `Jakarta Barat`, `Jakarta Selatan`,
`Area DKI Jakarta`, etc. in one go.

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

For each site, the runner prints how many jobs survived the filter:

```
[jobstreet:software-engineer] filter={'location': ['jakarta', 'bandung']} kept 1/5 (dropped 4)
```

Each site payload (`filtered_results[*].payload` in Mongo, and the CLI's stdout) also records the filter that was applied:

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
  location: [jakarta, bekasi, tangerang, depok, bogor]
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
runtime log shows `kept N/M (dropped X)` per site so you can tell which
filter is doing the cutting.
