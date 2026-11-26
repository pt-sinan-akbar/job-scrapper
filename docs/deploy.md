# Deploy

Woodpecker builds **one** Docker image, `job-scraper` (`infra/docker/Dockerfile`
stage `app`), and pushes it to GitHub Container Registry:

| Pipeline | Trigger | Image |
|---|---|---|
| `.woodpecker/dev.yml` | push to `dev` | `ghcr.io/pt-sinan-akbar/job-scraper/dev:<sha>` |
| `.woodpecker/prod.yml` | push to `main` | `ghcr.io/pt-sinan-akbar/job-scraper/prod:<sha>` |

Nothing deploys the image automatically.

## What ships

| Image | Container | Role |
|---|---|---|
| `job-scraper` | `job-scraper` (compose) or one cluster container | default command `/app/scripts/start-servers.sh`, MCP on 8080 and UI on 8090 in one container, exits when either one stops |

## Changing config

Job settings and Discord settings live in Mongo. The rest is baked in:

| Want to… | How |
|---|---|
| Change sites, or a site's limit, max age, filter | Edit at `/config`. Applies from the next run, no deploy |
| Change keywords | Not a setting. Type them in "Start a run", or pass them to `scrape_jobs` on every run |
| Change the proxy | Update `PROXY_URL` in `.env` → recreate the scraper service |
| Change concurrency | Update `SCRAPER_CONCURRENCY` in `.env` (1 to 10, default 2) → recreate the scraper service |
| Change the schedule | Scheduled runs come from a separate service outside this project. This project has no scheduler |
| Change Discord job format | Edit the template in the Discord section of `/config`. It fills each job in the attached `jobs-YYYY-MM-DD.md` file. Read fresh each send, no deploy |
| Change Discord max chars | Kept for older setups. Job sends ignore it and put every job in full in the attached file |
| Change Discord token or channel | Edit the Discord section of the UI. Stored in Mongo `discord_settings`, no deploy |

Note: `update_config` MCP tool writes go to Mongo and survive deploys.

## Job settings migration is one-way

The first read by this image moves old global `limit`, `concurrency`,
`max_age_hours`, `filter` and `keywords` into the sites and deletes the
global keys. It also renames `default_fields` to `fields` and drops per-site
`fields` overrides (see
[`configuration.md`](configuration.md#migration-from-global-values)). Older
images need those global keys, so after the migration they cannot read the
settings. Rolling back the image alone is not enough: restore the document too.

The original document is kept once as `_id: "active_pre_migration_backup"` in
`job_settings`. To restore it, stop the scraper containers, then in `mongosh`:

```js
use job_scraper
const backup = db.job_settings.findOne({ _id: "active_pre_migration_backup" })
db.job_settings.replaceOne(
  { _id: "active" },
  { version: backup.version, settings: backup.settings,
    updated_at: backup.updated_at, updated_by: backup.updated_by }
)
```

Then start the old image. Changes saved after the migration are lost. Starting
this image again migrates the restored document again; the backup is kept as
it was. A backup made by an earlier migration is never replaced, so after the
`default_fields` rename the backup may still be the document from before the
global value migration.

## Local sanity check

### Quick image build

Build the image locally before pushing to main:

```bash
docker build -f infra/docker/Dockerfile --target app -t job-scraper:local .
docker run --rm -p 8080:8080 job-scraper:local
```

If it boots, the same Dockerfile target will build in CI.

### End-to-end test

Start the dev stack and run a scrape from the UI:

```bash
./infra/scripts/manage.sh start     # mongo, mcp, ui, hot reload at http://localhost:5174
```

To test Discord, turn on **Notify Discord** for a UI run. It uses the Discord
settings saved in the UI.

## Seeding reference data

The `wilayah` collection stores Indonesian administrative area codes
(91 599 rows, Kepmendagri No 300.2.2-2138 Tahun 2025). It is **not**
seeded by the deploy pipeline — run this once on a fresh MongoDB or
after a data refresh.

### Prerequisites

- SSH tunnel to the VPS MongoDB (port 27017) active locally
- Node.js installed locally
- `mongodb` npm package: `npm install -g mongodb` (or local)

### Open tunnel

**DataGrip**: connect the data source — the SSH tunnel stays open while
DataGrip is connected. Note the local port it binds (visible in the
SSH/SSL tab of the data source settings).

**Manual**:
```bash
ssh -L 27017:localhost:27017 ubuntu@43.157.226.237 -N
```

### Run the seeder

```bash
MONGO_URI="mongodb://admin:<MONGO_ROOT_PASSWORD>@127.0.0.1:<LOCAL_PORT>/?authSource=admin" \
NODE_PATH=$(npm root -g) \
node seeds/wilayah.runner.js
```

- `MONGO_ROOT_PASSWORD` — root password of the target Mongo
- `LOCAL_PORT` — `27017` for manual tunnel; check DataGrip SSH/SSL tab if using DataGrip

The script drops the existing `wilayah` collection, inserts all batches,
creates a `nama` index, and verifies the exact row count. It exits
non-zero on mismatch.

### Restart after reseeding

The location filter reads `wilayah` the first time it needs it and then keeps
that copy in memory until the process stops. The MCP and UI processes in `job-scraper`
each hold their own copy, because the UI runs `scrape_jobs` in its own
process. After reseeding, restart the container so both read the new data:

```bash
docker restart job-scraper
```

### Seed job settings

Run this once on a fresh MongoDB, and before the first deploy that reads job settings. It only inserts when the document is missing.

```bash
MONGO_HOST=127.0.0.1 MONGO_PORT=<LOCAL_PORT> MONGO_ROOT_PASSWORD=<MONGO_ROOT_PASSWORD> ./seed.sh job-settings
```

Without this document, scrapes stop with a message that names this command.
