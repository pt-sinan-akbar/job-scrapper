# What is this

Personal job scraper for job boards (JobStreet, Glints, LinkedIn, Indeed,
Upwork). Flow: a Playwright/Python scraper is exposed as an **MCP HTTP server**
(`scraper-mcp`, port 8080) and a web control panel (`scraper-ui`, port 8090).
MCP scrape runs are recorded in **MongoDB**. Discord posting goes through a UI run with
**Notify Discord** or the MCP `send_discord_message` tool. Scheduled runs come
from a separate service outside this project.

One Docker image, `job-scraper` (Dockerfile stage `app`), holds the scraper, the
MCP server, the UI server, and the built UI. Its default command is
`python -m mcp_server.server`. The UI runs `python -m ui_server` from the same
image, and the CLI runs `python -m scraper`. Mongo uses the `mongo:7` image.
Driven by job settings in Mongo (default fields, and per-site limit, max age and filter), edited at /config. Concurrency comes from the `SCRAPER_CONCURRENCY` env var. Keywords are not a setting: every run names its own (the "Start a run" box in the UI, the required `keywords` argument of the MCP `scrape_jobs` tool, or `--keyword` on the CLI), and a run without keywords is refused with `keywords are required`.

Upwork is API-only. It uses the visitor GraphQL endpoint with no login and has no HTML fallback, so a failure shows up in `errors` with 0 jobs.

# How to run locally

Prereqs: Docker + Docker Compose, a Python venv.

Launch the interactive Docker manager TUI:

```bash
python scripts/manage.py
```

**TUI deps are separate from the runtime (Docker image) deps.** Install them first:

```bash
pip install -r scripts/requirements.txt   # textual + pyyaml — NOT the root requirements.txt
```

The root `requirements.txt` is baked into the Docker image and is not needed on the host.

The TUI is a single Textual screen with:

- **Env bar** — `dev` / `prod` buttons (default `dev`, from `scripts/environments.yaml`)
- **Summary panel** — shows the site names from `seeds/job_settings.yaml`, proxy status, mongo db/collection, masked `.env` secrets
- **Command preview panel** — shows the exact command that will run when you press a button
- **Action rows** — one row per scope (`all`, `mcp`, `mongo`, `ui`); columns: Start / Stop (labelled **Down** on the `all` row) / Status / Logs
- **Tests row** — dev smoke tests: Scrape / Mongo
- Keys: `q`/`ctrl+c` quit, `c` cancel running command, `r` refresh status, `x`/`ctrl+l` clear log

Equivalent raw command to start the MCP stack in dev (the TUI does this for you):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile mcp up --build -d
```

Before first run, copy the `.example` files (see section below).

# Test with a local MCP client

This is for an MCP client you run on your host machine (for example `claude` in
your laptop terminal, in the repo dir) to talk to the dockerized MCP server —
handy for ad-hoc testing.

It works because `scraper-mcp` publishes its port to the host
(`docker-compose.yml`: `ports: "8080:8080"`), so `localhost:8080` on your host
forwards into the container.

Create a project-root `.mcp.json` (gitignored):

```json
{
  "mcpServers": {
    "job-scraper": {
      "type": "http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

Start the MCP server first (TUI → `mcp` → Start, or the raw command in
[How to run locally](#how-to-run-locally)), then verify:

```bash
curl http://localhost:8080/health
```

# MCP on Docker

Containers reach the MCP server by name, not `localhost` — `localhost` inside a
container refers to the container itself, not the host.

- `scraper-ui` does not call the MCP server. It runs the scrape, config and Discord
  functions in its own process, so it needs `MONGO_URI`, `MONGO_DB_NAME`,
  `MONGO_COLLECTION_NAME` and `PROXY_URL` like `scraper-mcp`
- Dev: the job-agent backend uses `http://job-scraper-mcp:8080/mcp` on the shared `job-net` network
- Prod: `scraper-mcp` and `scraper-ui` both use `network_mode: host` and listen on
  `MCP_BIND_HOST` (default `172.17.0.1`). Caddy reaches the UI at `host.docker.internal:8090`

# Ports used here

| Service       | Port  | Bind                                      | Notes                                                    |
| ------------- | ----- | ----------------------------------------- | -------------------------------------------------------- |
| `scraper-mcp` | 8080  | `0.0.0.0:8080` (dev); host network (prod) | MCP HTTP; `/health` and `/mcp` endpoints                 |
| `scraper-ui`  | 8090  | `127.0.0.1:8090` (dev); host network (prod) | profile `ui`; in prod binds `MCP_BIND_HOST:8090`, public traffic goes through Caddy (80, 443) |
| `mongo`       | 27017 | `127.0.0.1:27017`                         | profiles `mcp`, `mongo`; data in `mongo-data` volume     |

# Copy the .example files

| Example                         | Copy to                 | Purpose                                                          |
| ------------------------------- | ----------------------- | ---------------------------------------------------------------- |
| `.env.example`                  | `.env`                  | local compose env vars: Mongo creds, `PROXY_URL`, UI dev login   |
| `scripts/ssh-tunnel.sh.example` | `scripts/ssh-tunnel.sh` | reverse SOCKS proxy helper — gitignored, contains real host/user |

`.env` is for local Docker Compose only. Production injects all env vars through
GitHub Actions secrets/variables — it never reads this file.

**MongoDB connection URL:** the app reads `MONGO_URI` (`mcp_server/mongo.py`). Set it
in `.env` locally and in the `MONGO_URI` GitHub secret in prod:

- dev / bridge network (`docker-compose.yml`): `mongodb://<user>:<password>@mongo:27017`
- prod / host network (`docker-compose.prod.yml`): `mongodb://<user>:<password>@localhost:27017`

The bundled `mongo` service still creates its admin login from `MONGO_ROOT_USER` and
`MONGO_ROOT_PASSWORD`. They are not in `.env`: export them in your shell before
`docker compose --profile mcp up`, or set them as GitHub secrets and variables in prod.

Outside Docker the code default is `mongodb://localhost:27017`.

# Seed reference data

Run after MongoDB is up:

```bash
./seed.sh                                          # local (reads .env)
MONGO_HOST=127.0.0.1 MONGO_PORT=27018 ./seed.sh   # prod via SSH tunnel
```

`./seed.sh job-settings` runs only the job settings seed, and `./seed.sh wilayah` runs only the area codes.

The wilayah seed drops and recreates its collection on each run. The job settings seed only inserts when the document is missing, so it never overwrites your edits. It needs `.venv`, or a Python path in `SCRAPER_PYTHON`.

**`wilayah`** — 91 599 Indonesian administrative region codes (Kepmendagri No 300.2.2-2138
Tahun 2025). Source: [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah/tree/6ff9b8a2764cd4fbeb8c15fe0cba2d5a4eb26107)
([wilayah.sql](https://raw.githubusercontent.com/cahyadsn/wilayah/6ff9b8a2764cd4fbeb8c15fe0cba2d5a4eb26107/db/wilayah.sql)).
Runner: `seeds/wilayah.runner.js` (Node.js, requires `mongodb` package).

# SSH tunnel (reverse SOCKS proxy)

`scripts/ssh-tunnel.sh` opens a **reverse dynamic SOCKS5** tunnel (`ssh -R`) so
the remote scraper routes its outbound HTTP traffic through **this machine's**
residential IP, dodging datacenter-IP blocks that jobstreet/glints/linkedin apply
to cloud VPS addresses.

`PROXY_URL` is `socks5://localhost:1080` in prod. In prod, `scraper-mcp` runs
`network_mode: host`, so `localhost:1080` on the remote server is the tunnel
endpoint provided by this script.

Setup:

```bash
cp scripts/ssh-tunnel.sh.example scripts/ssh-tunnel.sh
# Edit the file: set SSH_HOST and SSH_USER (or export them as env vars)
```

Commands:

```bash
./scripts/ssh-tunnel.sh up           # open the reverse SOCKS proxy
./scripts/ssh-tunnel.sh down         # close it
./scripts/ssh-tunnel.sh status       # proxy + mongo tunnel liveness + docker ps
./scripts/ssh-tunnel.sh test         # verify remote traffic exits via this machine's IP
./scripts/ssh-tunnel.sh mongo-up     # forward local :27018 → remote MongoDB
./scripts/ssh-tunnel.sh mongo-down   # close the mongo forward tunnel
./scripts/ssh-tunnel.sh mongo-status # show mongo tunnel liveness
./scripts/ssh-tunnel.sh mongo-test   # verify port reachable + mongosh ping
./scripts/ssh-tunnel.sh mongo-reset  # reset remote mongo root password (see below)
```

The `test` command confirms the proxied egress IP differs from the server's
direct egress IP. If they match, the tunnel is not working.

## Connecting to prod MongoDB from local machine

Prod MongoDB binds to `127.0.0.1:27017` on the server — not exposed publicly.
Use `mongo-up` to open a forward tunnel, then connect normally:

```bash
./scripts/ssh-tunnel.sh mongo-up
mongosh "mongodb://admin:<MONGO_ROOT_PASSWORD>@127.0.0.1:27018"
```

Any client connecting from outside the server (DataGrip, DBeaver, Compass, Python scripts)
must go through the tunnel the same way — run `mongo-up` first, then connect using
`mongodb://<user>:<password>@127.0.0.1:27018`. Verify with `mongo-test`:

```bash
./scripts/ssh-tunnel.sh mongo-up
./scripts/ssh-tunnel.sh mongo-test
```

Default local port is `27018` (not `27017`) to avoid conflict with a running dev
mongo container. Override if needed:

```bash
MONGO_PORT=27019 ./scripts/ssh-tunnel.sh mongo-up
```

### "Authentication failed" against prod mongo

If `mongo-test` reports auth failure (and `job-scraper-mcp` shows `unhealthy`)
even though `MONGO_ROOT_PASSWORD` looks correct, the volume was **first**
initialized with different creds. `MONGO_INITDB_ROOT_USERNAME` / `_PASSWORD`
only apply on the **first** mongod start against an **empty** `mongo-data`
volume — once data exists, mongod stores creds in the volume and ignores those
env vars forever. So changing the GitHub secret and redeploying has **no
effect** on the password.

Fix in place (keeps data) — reset the stored password to `MONGO_ROOT_PASSWORD`:

```bash
./scripts/ssh-tunnel.sh mongo-reset
```

This SSHes in, stops the authed mongo, boots a throwaway no-auth mongo on the
same volume, sets the `admin` password, then restarts the real container (a
`trap` restarts it even if a step fails). Re-run `mongo-test` to confirm.

Alternative (clean slate, **loses scrape history**): remove the container +
volume so the next start re-initializes from current env:

```bash
docker rm -f job-scraper-mongo && docker volume rm job-scrapper_mongo-data
# then redeploy, or `docker compose ... --profile mcp up -d`
```

# Deployment process

`.github/workflows/deploy.yml` — triggers on push to `main` or manual
`workflow_dispatch`.

**Build job** (`build`):

- Builds the Dockerfile `app` stage and pushes one image to `ghcr.io`
- Two tags: rolling `:latest` and immutable per-commit `:<sha>`
- Uses GitHub Actions layer cache to speed up rebuilds

**Deploy jobs** (both use the sha tag through `SCRAPER_IMAGE`):

1. `deploy-mcp` (needs `build`): copies `docker-compose.yml` + `docker-compose.prod.yml` to the server via SCP, then SSHs in and runs `docker compose --profile mcp pull && up -d --no-build`
2. `deploy-ui` (needs `build` + `deploy-mcp`): same flow for `--profile ui`, plus the `Caddyfile`. Skipped when the `UI_DOMAIN` variable is not set

Woodpecker (`.woodpecker/dev.yml`, `.woodpecker/prod.yml`) builds the same `app`
stage and pushes `ghcr.io/pt-sinan-akbar/job-scraper/dev` or `/prod`.

# Config: Mongo and the proxy var

Settings live in three places, by how they change

| Place | Holds | Change it |
| --- | --- | --- |
| `job_settings` collection | `default_fields`, `sites`. Each site has its own `limit` (required), `max_age_hours` and `filter`; there are no global values | `/config` page, applies from the next run |
| `PROXY_URL` env var | Proxy URL. Empty means direct connection. Not set stops scrapes | `.env` in dev, GitHub variable in prod |
| `SCRAPER_CONCURRENCY` env var | How many `(keyword, site)` pairs run at once, 1 to 10, default 2. Invalid values log a warning and use 2 | `.env` in dev, GitHub variable in prod |
| `discord_settings` collection | Discord token, channel, `message_template`, `max_chars` | Discord section of `/config`. Unset template and cap use the defaults in `mcp_server/discord_settings.py` |

Each host's Mongo has its own document, so dev and prod differ without a patch file. A new environment needs one seed

    ./seed.sh job-settings

`seeds/job_settings.yaml` is only the first version. After seeding, `/config` is the source. `url_template` can change only through the `update_config` MCP tool

An older document that still has global `limit`, `concurrency`, `max_age_hours`, `filter` or `keywords` is migrated on its first read: the values move into each site that lacks them (a site with no usable limit gets the global one, else `2`), limits are clamped to 1..200, the global keys are deleted, and the result is validated and saved once with the next version and `updated_by: "migration"`. The original is kept once as `active_pre_migration_backup`. The migration is one-way for older images; see [`docs/deploy.md`](docs/deploy.md#job-settings-migration-is-one-way) to restore. See [`docs/configuration.md`](docs/configuration.md#migration-from-global-values)

Nothing is written to disk. `scrape_jobs` gets each site's results straight from the runner and stores them in Mongo

# How the filter works

Each site's `filter` runs **after** scraping — not at the HTTP/URL level.
URL templates carry no location params. All search-page results are fetched and
parsed first, then filtered in Python.

Pipeline in `run_one` (`scraper/runner.py`):

1. Fetch search page (full HTTP request)
2. Parse all jobs from HTML
3. Drop jobs older than the site's `max_age_hours` (none dropped when it is not set)
4. **`apply_filter`** — drop jobs not matching the site's `filter` (none dropped when it is empty)
5. Fetch detail pages — only for jobs that survived step 4
6. Return the site's payload to the caller

`apply_filter` (`scraper/sites/_filter.py`) does case-insensitive substring
matching per field. `location: [jakarta, tangerang]` keeps a job if
`job["location"].lower()` contains any of those strings.

Edge case: if a job's filtered field is `None` (site didn't return it), the
job passes through — it is not dropped.

# Scheduled runs

This project has no scheduler. Scheduled runs come from a separate service
outside this project (a Kubernetes CronJob in another repo).

To run a scrape by hand, start one from the UI, or scrape only (no Mongo write,
no Discord post):

```bash
# Via TUI: tests row → Scrape

# Or directly (--keyword is required, repeat it for several):
docker exec job-scraper-mcp python -m scraper --keyword "software engineer"
```

The CLI prints every site's filtered payload as JSON on stdout, so it pipes into `jq`.
Logs go to stderr

```bash
docker exec job-scraper-mcp python -m scraper --keyword "software engineer" jobstreet | jq '.[].payload.count'
```

Without `--keyword` the CLI prints `keywords are required` to stderr and exits `2`.

# Query MongoDB data

Connect to the Mongo shell:

```bash
docker exec -it job-scraper-mongo mongosh -u admin -p <MONGO_ROOT_PASSWORD> --authenticationDatabase admin
```

Then query the scrape history:

```js
use job_scraper

// all runs
db.scrape_runs.find({})

// latest first
db.scrape_runs.find({}).sort({ _id: -1 })

// count
db.scrape_runs.countDocuments()

// latest single run
db.scrape_runs.findOne({}, {}, { sort: { _id: -1 } })
```

# Clear / reset MongoDB data

⚠️ **Irreversible.** In MongoDB, columns (fields) live on the documents, not in a
fixed schema — deleting the documents removes the old fields with them. After a
wipe, only the columns the current code writes reappear on the next run.

Connect to the Mongo shell (same `docker exec … mongosh` as
[Query MongoDB data](#query-mongodb-data)), then:

```js
use job_scraper

// empty the collection — keeps it and its indexes (recommended)
db.scrape_runs.deleteMany({})

// or drop the collection (removes documents + indexes)
db.scrape_runs.drop()

// or drop the whole database
db.dropDatabase()
```

For **prod**, open the SSH tunnel first (see
[Connecting to prod MongoDB from local machine](#connecting-to-prod-mongodb-from-local-machine)),
then run the same commands.

# Check logs

Stream container logs:

```bash
docker logs -f job-scraper-mcp       # MCP server
docker logs -f job-scraper-ui        # Scraper UI
docker logs -f job-scraper-mongo     # MongoDB
```

Via TUI: select a scope row → **Logs** (runs `docker compose … logs -f --tail=200 <services>`).

# Smoke tests

The full MCP tool list is in [docs/mcp.md](docs/mcp.md). Quick checks from the TUI tests row:

| Button      | What it tests                                                                               |
| ----------- | ------------------------------------------------------------------------------------------- |
| **Scrape**  | Runs `python -m scraper --keyword "software engineer"` in `scraper-mcp` — scrape only, no Mongo write, no Discord post |
| **Mongo**   | Inserts + reads + drops a throwaway document in `scraper-mcp` via the real Mongo connection |

# Scraper UI

Web control panel for this repo: run scrapes, see results, and edit config.
It does not depend on the job-agent frontend or backend.

Start it in dev with Vue hot reload, then open http://localhost:5174:

    ./scripts/run_dev.sh

This starts `scraper-mcp` and `scraper-ui` in Docker, then runs the Vite dev server in
the foreground. Ctrl+C stops Vite only, the containers keep running.
http://127.0.0.1:8090 serves the UI baked into the image, so it only changes after a rebuild.

- Runs go through `scraper-mcp`, one at a time, with no stop button
- The latest UI run (record, jobs, failures, raw and filtered payloads) is saved in the
  Mongo `ui_runs` collection, so it survives a restart. Only one run is kept, and UI runs
  never go to `scrape_runs`. If Mongo is down, the result lives in memory only, run storage is skipped for 30 s after a failure, and reading an older run by id returns 503.
  API: `GET /api/runs/latest` and `GET /api/runs/{id}`, see [`docs/architecture.md`](docs/architecture.md#scraper-ui-api-ui_server)
- A run with **Notify Discord** on posts its jobs to Discord, using the Discord settings saved in the UI
- Config saves go through `scraper-mcp` into Mongo. Saving is off while a scrape runs, because MCP is busy then
- Prod is public through Caddy with one password
- Compose needs the external `job-net` network. The scripts in `scripts/` create it.
  With plain `docker compose` or `scripts/manage.py`, run `docker network create job-net`
  once first

# GitHub Actions variables & secrets

Set these in your repository's **Settings → Secrets and variables**.

**Secrets** (encrypted, never logged):

| Secret                | Required by | Purpose                                |
| --------------------- | ----------- | -------------------------------------- |
| `SSH_HOST`            | deploy jobs | Server IP or hostname                  |
| `SSH_USER`            | deploy jobs | SSH login user                         |
| `SSH_PRIVATE_KEY`     | deploy jobs | Private key for SSH authentication     |
| `MONGO_ROOT_PASSWORD` | deploy-mcp  | MongoDB root password                  |
| `MONGO_URI`           | deploy-mcp  | MongoDB connection URL                 |
| `GITHUB_TOKEN`        | build job   | Auto-provided; used to push to ghcr.io |

**Variables** (plain text, shown in logs):

| Variable                | Default       | Purpose                   |
| ----------------------- | ------------- | ------------------------- |
| `MONGO_ROOT_USER`       | `admin`       | MongoDB root username     |
| `MONGO_DB_NAME`         | `job_scraper` | Database name             |
| `MONGO_COLLECTION_NAME` | `scrape_runs` | Scrape history collection |
