# Deploy pipeline

GitHub Actions builds **one** Docker image, `job-scraper` (Dockerfile stage
`app`), pushes it to GitHub Container Registry, and SSHs into the VPS to
(re)create the containers with `docker compose`.

Trigger: push to `main` (or manual via "Run workflow" in the Actions tab).

Each deploy copies `docker-compose.yml` and `docker-compose.prod.yml` to
`~/scraper` on the VPS and starts the containers fresh from the new image.
Secrets come in as env vars from GitHub.

## What ships

| Image | Container | Role |
|---|---|---|
| `ghcr.io/<owner>/<repo>:<sha>` | `job-scraper-mcp` | default command `python -m mcp_server.server`, FastMCP HTTP server on port 8080 |
| same image | `job-scraper-ui` | `command: ["python", "-m", "ui_server"]`, UI on port 8090, behind Caddy |

The image is also tagged `:latest`. Both deploy jobs get the sha tag through
`SCRAPER_IMAGE`.

## What the pipeline does

1. **build** — build the `app` Dockerfile target → push `:latest` and `:<sha>`
2. **deploy-mcp** — SSH, `docker compose --profile mcp pull` + `up -d --no-build`
3. **deploy-ui** — SSH, same for `--profile ui`, which also starts Caddy. Skipped when the `UI_DOMAIN` variable is not set

deploy-ui runs after deploy-mcp, so two deploys never touch the VPS at the
same time.

Woodpecker (`.woodpecker/dev.yml`, `.woodpecker/prod.yml`) builds the same `app`
target and pushes `ghcr.io/pt-sinan-akbar/job-scraper/dev` or
`ghcr.io/pt-sinan-akbar/job-scraper/prod`.

## Required GitHub secrets

Repo → Settings → Secrets and variables → Actions → **Secrets** tab.

| Secret | Used by | Value |
|---|---|---|
| `SSH_HOST` | all deploy jobs | `43.157.226.237` |
| `SSH_USER` | all deploy jobs | `ubuntu` |
| `SSH_PRIVATE_KEY` | all deploy jobs | private key for VPS SSH |
| `GHCR_PULL_TOKEN` | all deploy jobs | GitHub token with `read:packages` scope, so the VPS can pull private images |
| `UI_PASSWORD_HASH` | deploy-ui | Required when `UI_DOMAIN` is set. Argon2 hash of the UI password, see `.env.example` |
| `UI_SESSION_SECRET` | deploy-ui | Required when `UI_DOMAIN` is set. Random string, at least 32 characters, see `.env.example` |

`GITHUB_TOKEN` is auto-provided — used to push to ghcr.io.

## Required GitHub variables

Same UI, but the **Variables** tab. Plain text (visible in logs and to
anyone with read access). Use these for non-secret config:

| Variable | Used by | Value |
|---|---|---|
| `UI_DOMAIN` | deploy-ui | Optional. Public domain for the UI, with DNS pointing to the VPS. When it is not set, deploy-ui is skipped and the UI stays offline |
| `MCP_BIND_HOST` | all deploy jobs | Optional. Docker gateway IP of the VPS, default `172.17.0.1` |
| `SCRAPER_CONCURRENCY` | all deploy jobs | Optional. How many `(keyword, site)` pairs a scrape runs at once, 1 to 10, default `2`. An invalid value logs a warning and uses 2 |
| `PROXY_URL` | `deploy-mcp` | Required. Proxy URL for scrapes, such as `socks5://localhost:1080`. A URL with a password belongs in a secret of the same name, because variables are visible in logs. The deploy fails when it is missing or empty |

## Networking

scraper-mcp and scraper-ui both use `network_mode: host`, because `MONGO_URI`
and `PROXY_URL` point to `localhost` on the VPS. Both listen on the Docker gateway
address (`MCP_BIND_HOST`, default `172.17.0.1`), so containers on the VPS reach
them through `host.docker.internal` and the public cannot. Do not set it to
`127.0.0.1`, which would cut off Caddy and other containers.

scraper-ui does not call scraper-mcp. It runs the scrape, config and Discord
functions in its own process, so deploy-ui passes it `MONGO_URI`,
`MONGO_DB_NAME`, `MONGO_COLLECTION_NAME`, `PROXY_URL` and `SCRAPER_CONCURRENCY`. Caddy reaches the UI at
`host.docker.internal:8090`.

scraper-ui has no published port. Caddy is its only public entry, on ports 80 and
443. The UI is optional: deploy-ui runs only when the `UI_DOMAIN` variable is set.
Required before you set it: `UI_PASSWORD_HASH` and `UI_SESSION_SECRET` secrets,
and a DNS record pointing to the VPS.

## ghcr.io image visibility

The first push creates the package as **private**, and it stays private.
Each deploy job logs in to ghcr.io on the VPS with `GHCR_PULL_TOKEN`, pulls the
image, and logs out when it ends.

Do not rely on a saved `docker login` on the VPS. The job-agent backend and
frontend deploys run on the same VPS and log out of ghcr.io when they finish,
which removes any saved login.

## Changing config

Job settings and Discord settings live in Mongo. The rest is baked in:

| Want to… | How |
|---|---|
| Change sites, or a site's limit, max age, filter | Edit at `/config`. Applies from the next run, no deploy |
| Change keywords | Not a setting. Type them in "Start a run", or pass them to `scrape_jobs` / `--keyword` on every run |
| Change the proxy | Update the `PROXY_URL` GitHub secret or variable → redeploy |
| Change concurrency | Update the `SCRAPER_CONCURRENCY` GitHub variable (1 to 10, default 2) → redeploy. Locally, set it in `.env` and recreate scraper-mcp and scraper-ui |
| Change the schedule | Scheduled runs come from a separate service outside this project. This project has no scheduler |
| Change Discord message format | Edit the template in the Discord section of `/config`. Read fresh each send, no deploy |
| Change Discord per-message cap | Edit max chars in the Discord section of `/config` |
| Change Discord token or channel | Edit the Discord section of the UI. Stored in Mongo `discord_settings`, no deploy |

Note: `update_config` MCP tool writes go to Mongo and survive deploys.

## Manual rollback

To roll back to a previous SHA, trigger the workflow on that older
commit (Actions tab → "Run workflow" → choose ref).

Or directly on the VPS:

```bash
ssh ubuntu@<host>
cd ~/scraper
export SCRAPER_IMAGE=ghcr.io/<owner>/<repo>:<previous-sha>
C="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$C --profile mcp pull && $C --profile mcp up -d --no-build
$C --profile ui pull && $C --profile ui up -d --no-build
```

The MCP step also needs the env vars from the workflow (`MONGO_URI`,
`PROXY_URL`, ...). Log in to ghcr.io first, see above. Rolling back past the
job settings migration also needs the settings document restored, see
[Job settings migration is one-way](#job-settings-migration-is-one-way).

## Job settings migration is one-way

The first read by this image moves old global `limit`, `concurrency`,
`max_age_hours`, `filter` and `keywords` into the sites and deletes the
global keys (see
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
it was.

## Trigger flow

| Action | Result |
|--------|--------|
| Push commit to `main` | All 3 jobs run: build, deploy-mcp, deploy-ui (deploy-ui only when `UI_DOMAIN` is set) |
| PR merged into `main` | Same |
| Manual run | Actions tab → "Build & Deploy scraper" → Run workflow |
| Push to feature branch / `dev` | No deploy. Use PRs against `dev`, then merge `dev` → `main` for prod |

## Local sanity check

### Quick image build

Build the image locally before pushing to main:

```bash
docker build --target app -t job-scraper:local .
docker run --rm -p 8080:8080 job-scraper:local
```

If it boots, the same Dockerfile target will build in CI.

### End-to-end test

Start the dev stack and run a scrape from the UI:

```bash
./scripts/run_dev.sh          # mcp + ui, hot reload at http://localhost:5174
./scripts/run_dev.sh mcp      # MCP server only
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

- `MONGO_ROOT_PASSWORD` — value from your production `.env` / VPS secrets
- `LOCAL_PORT` — `27017` for manual tunnel; check DataGrip SSH/SSL tab if using DataGrip

The script drops the existing `wilayah` collection, inserts all batches,
creates a `nama` index, and verifies the exact row count. It exits
non-zero on mismatch.

### Seed job settings

Run this once on a fresh MongoDB, and before the first deploy that reads job settings. It only inserts when the document is missing.

```bash
MONGO_HOST=127.0.0.1 MONGO_PORT=<LOCAL_PORT> MONGO_ROOT_PASSWORD=<MONGO_ROOT_PASSWORD> ./seed.sh job-settings
```

Without this document, scrapes stop with a message that names this command.
