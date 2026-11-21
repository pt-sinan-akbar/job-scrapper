# What is this

Personal job scraper for job boards (JobStreet, Glints, LinkedIn, Indeed,
Upwork). Flow: a Playwright/Python scraper is exposed as an **MCP HTTP server**
(`scraper-mcp`, port 8080) and a web control panel (`scraper-ui`, port 8090).
MCP scrape runs are recorded in **MongoDB**. Discord posting goes through a UI run with
**Notify Discord** or the MCP `send_discord_message` tool. Scheduled runs come
from a separate service outside this project.

One Docker image, `job-scraper` (`infra/docker/Dockerfile` stage `app`), holds the scraper, the
MCP server, the UI server, and the built UI. Its default command is
`python -m mcp_server.server`. The UI runs `python -m backend` from the same
image. Mongo uses the `mongo:7` image.
Driven by job settings in Mongo (one fields list for every site, and per-site limit, max age and filter), edited at /config. Concurrency comes from the `SCRAPER_CONCURRENCY` env var. Keywords are not a setting: every run names its own (the "Start a run" box in the UI, or the required `keywords` argument of the MCP `scrape_jobs` tool), and a run without keywords is refused with `keywords are required`.

Upwork is API-only. It uses the visitor GraphQL endpoint with no login and has no HTML fallback, so a failure shows up in `errors` with 0 jobs.

# How to run locally

Prereqs: Docker + Docker Compose, a Python venv.

Start the dev stack:

```bash
./infra/scripts/manage.sh start   # mongo, mcp, ui and Vite
./infra/scripts/manage.sh stop    # stop and remove the containers, data is kept
./infra/scripts/manage.sh         # pick start, restart or stop from a menu
```

Equivalent raw command to start the containers:

```bash
docker compose --project-directory . -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.dev.yml up --build -d
```

Before first run, copy the `.example` files (see section below).

# Test with a local MCP client

This is for an MCP client you run on your host machine (for example `claude` in
your laptop terminal, in the repo dir) to talk to the dockerized MCP server —
handy for ad-hoc testing.

It works because `scraper-mcp` publishes its port to the host
(`infra/compose/docker-compose.yml`: `ports: "8080:8080"`), so `localhost:8080` on your host
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

Start the stack first (`./infra/scripts/manage.sh start`, or the raw command in
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
- The job-agent backend uses `http://job-scraper-mcp:8080/mcp` on the shared `job-net` network

# Ports used here

| Service       | Port  | Bind                                      | Notes                                                    |
| ------------- | ----- | ----------------------------------------- | -------------------------------------------------------- |
| `scraper-mcp` | 8080  | `0.0.0.0:8080`                            | MCP HTTP; `/health` and `/mcp` endpoints                 |
| `scraper-ui`  | 8090  | `127.0.0.1:8090`                          | FastAPI backend serving the built frontend               |
| `mongo`       | 27017 | `127.0.0.1:27017`                         | data in `mongo-data` volume                              |

# Copy the .example files

| Example                         | Copy to                 | Purpose                                                          |
| ------------------------------- | ----------------------- | ---------------------------------------------------------------- |
| `.env.example`                  | `.env`                  | local compose env vars: Mongo creds, `PROXY_URL`, UI dev login   |

`.env` holds the env vars for Docker Compose.

**MongoDB connection URL:** the app reads `MONGO_URI` (`mcp_server/mongo.py`). Set it
in `.env`: `mongodb://<user>:<password>@mongo:27017`

The bundled `mongo` service still creates its admin login from `MONGO_ROOT_USER` and
`MONGO_ROOT_PASSWORD`. They are not in `.env`: export them in your shell before
`docker compose up`.

Outside Docker the code default is `mongodb://localhost:27017`.

# Seed reference data

Run after MongoDB is up:

```bash
./seed.sh                                          # local (reads .env)
MONGO_HOST=127.0.0.1 MONGO_PORT=27018 ./seed.sh   # remote Mongo via SSH tunnel
```

`./seed.sh job-settings` runs only the job settings seed, and `./seed.sh wilayah` runs only the area codes.

The wilayah seed drops and recreates its collection on each run. The job settings seed only inserts when the document is missing, so it never overwrites your edits. It needs `.venv`, or a Python path in `SCRAPER_PYTHON`.

After reseeding `wilayah`, restart `scraper-mcp` and `scraper-ui` (`docker restart job-scraper-mcp job-scraper-ui`). Each process loads the region list the first time a location filter needs it and keeps that copy until it stops, and the UI runs `scrape_jobs` in its own process, so both hold a copy.

**`wilayah`** — 91 599 Indonesian administrative region codes (Kepmendagri No 300.2.2-2138
Tahun 2025). Source: [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah/tree/6ff9b8a2764cd4fbeb8c15fe0cba2d5a4eb26107)
([wilayah.sql](https://raw.githubusercontent.com/cahyadsn/wilayah/6ff9b8a2764cd4fbeb8c15fe0cba2d5a4eb26107/db/wilayah.sql)).
Runner: `seeds/wilayah.runner.js` (Node.js, requires `mongodb` package).

# Deployment process

Woodpecker (`.woodpecker/dev.yml`, `.woodpecker/prod.yml`) builds the `infra/docker/Dockerfile`
`app` stage and pushes `ghcr.io/pt-sinan-akbar/job-scraper/dev` or `/prod`.
See [`docs/deploy.md`](docs/deploy.md).

# Config: Mongo and the proxy var

Settings live in three places, by how they change

| Place | Holds | Change it |
| --- | --- | --- |
| `job_settings` collection | `fields` (one list for every site), `sites`. Each site has its own `limit` (required), `max_age_hours` and `filter`; there are no global values | `/config` page, applies from the next run |
| `PROXY_URL` env var | Proxy URL. Empty means direct connection. Not set stops scrapes | `.env` |
| `SCRAPER_CONCURRENCY` env var | How many `(keyword, site)` pairs run at once, 1 to 10, default 2. Invalid values log a warning and use 2 | `.env` |
| `discord_settings` collection | Discord token, channel, `message_template`, `max_chars` | Discord section of `/config`. Unset template and cap use the defaults in `mcp_server/discord_settings.py`. Job sends ignore `max_chars` |

Each host's Mongo has its own document, so dev and prod differ without a patch file. A new environment needs one seed

    ./seed.sh job-settings

`seeds/job_settings.yaml` is only the first version. After seeding, `/config` is the source. `url_template` can change only through the `update_config` MCP tool

An older document that still has global `limit`, `concurrency`, `max_age_hours`, `filter` or `keywords` is migrated on its first read: the values move into each site that lacks them (a site with no usable limit gets the global one, else `2`), limits are clamped to 1..200, the global keys are deleted, and the result is validated and saved once with the next version and `updated_by: "migration"`. The original is kept once as `active_pre_migration_backup`. The migration is one-way for older images; see [`docs/deploy.md`](docs/deploy.md#job-settings-migration-is-one-way) to restore. See [`docs/configuration.md`](docs/configuration.md#migration-from-global-values)

Nothing is written to disk. `scrape_jobs` gets each site's results straight from the runner and stores them in Mongo

# How the filter works

Each site's `filter` runs **after** scraping — not at the HTTP/URL level.
URL templates carry no location params. All results are fetched first (from the
site's API or its search page), then filtered in Python.

Pipeline in `scrape_site_for_keyword` (`scraper/runner.py`):

1. Search through the site's API (`search_jobs_via_api`), when the site has a usable `api` block
2. If the API is not used or fails, download the search page through the HTML downloader chain (curl_cffi, then cloudscraper, then Playwright) and parse it (`scraper.parse(html)`). An API-only site (Upwork) fails here instead. A site that makes its own request (Indeed) skips the download: `scraper.parse("")` calls the site's API, and a failure is reported as `api failed: <code>`
3. Fill each job's missing `matched_keyword` and `posted_at`
4. Build the raw payload: every job found, before any cut
5. Drop jobs older than the site's `max_age_hours` (none dropped when it is not set)
6. **`filter_reason`** — drop jobs not matching the site's `filter` (none dropped when it is empty)
7. Keep only the first `limit` jobs
8. Fill `requirements` — only for jobs that survived step 7, and only when `requirements` is a saved field. Jobs from the API ask the detail API first, then the job page
9. Build the filtered payload and return both payloads to the caller

`filter_reason` (`scraper/sites/_filter.py`) checks each filter key. The
`location` key resolves names through the region index (the Mongo `wilayah`
list): `location: [jakarta, tangerang]` keeps a job whose location resolves to
a region under Jakarta or Tangerang. It falls back to substring matching only
when the index cannot be loaded. The other keys use case-insensitive substring
matching: `work_type: [remote, hybrid]` keeps a job if
`job["work_type"].lower()` contains any of those strings.

Edge case: if a job's filtered field is `None` (site didn't return it), the
job passes through — it is not dropped.

# Scheduled runs

This project has no scheduler. Scheduled runs come from a separate service
outside this project (a Kubernetes CronJob in another repo).

To run a scrape by hand, start one from the "Start a run" box in the UI, or call
the MCP `scrape_jobs` tool with its required `keywords` argument. `scrape_jobs`
saves the run in the Mongo `scrape_runs` collection, and skips the save when called
with `save_run=false`. The UI calls it with `save_run=false`, so a UI run is not
saved in `scrape_runs` and its `mongo_id` is null. The UI keeps its latest run in
its own `ui_runs` collection. A run without keywords is refused with
`keywords are required`.

`scrape_jobs` returns `results`, a flat list of `{keyword, site, payload}`
with one entry per keyword and site pair. A saved run holds `run_metadata`,
`results` and `note`. Raw results are not saved: `raw_results` exists only in
the `scrape_jobs` response with `include_raw_results=true`. Runs saved before
this change use `filtered_results` instead of `results` and may contain
`raw_results`, and the job-agent backend reads both. See
[`docs/mcp.md`](docs/mcp.md#scrape_jobs).

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

For a remote Mongo, open an SSH tunnel first
(`ssh -L 27018:localhost:27017 <user>@<host> -N`), then run the same commands.

# Check logs

Stream container logs:

```bash
docker logs -f job-scraper-mcp       # MCP server
docker logs -f job-scraper-ui        # Scraper UI
docker logs -f job-scraper-mongo     # MongoDB
```

The scraper logs to stdout only. There is no log file and no log rotation, so
`docker logs` is the only place to read them. A run started from the UI logs in
`job-scraper-ui`, because the UI runs `scrape_jobs` in its own process. An MCP
`scrape_jobs` call logs in `job-scraper-mcp`.

# Smoke tests

The full MCP tool list is in [docs/mcp.md](docs/mcp.md).

# Scraper UI

Web control panel for this repo: run scrapes, see results, and edit config.
It does not depend on the job-agent frontend or backend.

Start it in dev with Vue hot reload, then open http://localhost:5174:

    ./infra/scripts/manage.sh start

This starts `scraper-mcp` and `scraper-ui` in Docker, then runs the Vite dev server in
the foreground. Ctrl+C stops Vite only, the containers keep running.
http://127.0.0.1:8090 serves the UI baked into the image, so it only changes after a rebuild.

- Runs call `scrape_jobs` inside the `scraper-ui` process, one at a time, with no stop button
- The latest UI run (record, jobs, failures, filtered payloads) is saved in the
  Mongo `ui_runs` collection, so it survives a restart. Only one run is kept, and UI runs
  never go to `scrape_runs`. If Mongo is down, the result lives in memory only, run storage is skipped for 30 s after a failure, and reading an older run by id returns 503.
  API: `GET /api/scrapes/latest` and `GET /api/scrapes/{scrape_id}`, see [`docs/architecture.md`](docs/architecture.md#scraper-ui-api-backend)
- A run with **Notify Discord** on posts one Discord message, using the Discord settings saved in the UI. The message is a job digest with a `jobs-YYYY-MM-DD.md` file attached that holds every job. A run with 0 jobs or a failed run posts a short text message instead. See [`docs/orchestration.md`](docs/orchestration.md#what-a-job-send-posts)
- **Send last result** on the Discord page posts the same digest for the latest finished run to the default channel again (`POST /api/scrapes/latest/discord`)
- Config saves go through `scraper-mcp` into Mongo. Saving is off while a scrape runs, because MCP is busy then
- Compose needs the external `job-net` network. The scripts in `infra/scripts/` create it.
  With plain `docker compose`, run `docker network create job-net`
  once first
