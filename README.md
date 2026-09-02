# Water Meter Dashboard

A full-stack water meter tracking and analysis app with AI-powered analysis.

- **Frontend:** React 19 + Vite + Tailwind CSS
- **Backend:** FastAPI + PostgreSQL (primary store)
- **AI:** Anthropic Claude or OpenAI GPT-4o (your API key, never stored on server)

---

## Features

### Core
- Import PDF water bills using AI extraction (Claude or GPT-4o)
- Import meter readings from CSV files (multi-file, format auto-detection, preview step, automatic duplicate/conflict detection against existing readings, with bulk conflict resolution)
- Dashboard with consumption, cost, and spike summary cards
- Usage charts and anomaly/spike detection across all meters
- Household sum verification against billing statements, plus a "Money Lost to Unaccounted Water" chart showing the $ gap between billed and summed household consumption
- Manual reading entry, search/filter, and CSV export

### Daily Leak Detection
A short-term workspace for spotting leaks between bills, kept completely separate from the monthly billing data above — nothing imported here touches the `Readings` table or billing statements.

- Import daily **submeter** readings and daily **main meter** readings (AMI "range export" CSV) into an active session
- Automatic daily-delta comparison: sums all submeter deltas and checks them against the main meter's delta for the same period
- Flags a **potential leak** whenever the submeter total exceeds the main meter, with a comparison line chart and a per-day table
- Below that comparison, an **SFPUC / EyeOnWater Main Meter Rules** section runs three official leak-detection rules against the main meter's own readings — 24h continuous flow, 48h/72h volume threshold, and nighttime usage ratio — main meter only, since submeter data is manually read and too sparse for these rules to ever apply
- **Archive Session** clears the active workspace for a fresh investigation while keeping the archived data viewable
- **Restore** brings an archived session back as the active workspace at any time

See [Using Daily Leak Detection](#using-daily-leak-detection) below for the full workflow.

### AI Assistant
Chat with AI about your data using Claude or GPT-4o — natural language Q&A against your readings, bills, and leak detection sessions.

---

## Running with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A PostgreSQL database (e.g. a managed instance like AWS RDS) and its connection string

### Set up the database

Recommended: one Postgres instance, a separate database per environment (prod, dev, test), each owned by its own role — so a misconfigured `DATABASE_URL` on a dev machine can't accidentally read or write real data. `PUBLIC`'s default `CONNECT` privilege on the prod database is revoked, so only the intended role can even open a connection to it.

```sql
-- One-time, run as the instance's admin/master user:
CREATE ROLE dev_app LOGIN PASSWORD '<random>';
GRANT dev_app TO <admin_user>;              -- RDS requires this before OWNER TO below
CREATE DATABASE water_meter_dev OWNER dev_app;

CREATE ROLE test_app LOGIN PASSWORD '<random>';
GRANT test_app TO <admin_user>;
CREATE DATABASE water_meter_test OWNER test_app;

REVOKE CONNECT ON DATABASE water_meter FROM PUBLIC;
GRANT CONNECT ON DATABASE water_meter TO <admin_user>;
```

Then:

1. Copy `.env.example` to `.env`. Set `DATABASE_URL` to the `dev_app`/`water_meter_dev` connection string for local dev, and `TEST_DATABASE_URL` to `test_app`/`water_meter_test`. `.env` is gitignored — never commit real credentials.
2. Create the schema with Alembic, once per database:
   ```bash
   cd backend
   pip install -r requirements.txt
   alembic upgrade head
   ```
   Re-run this after pulling changes that add a new Alembic revision, and again for any new database (test, a teammate's dev database, etc.).
3. The real deployment's `DATABASE_URL` points at `water_meter` using its own role — not `dev_app`/`test_app`, which are deliberately unable to reach it.

> `readings` has a unique constraint on `(mi, record_date)` (enforced at the DB level, not just by the CSV import UI). Upgrading a database that already has duplicate `(mi, record_date)` rows will fail that migration — check first:
> ```sql
> SELECT mi, record_date, COUNT(*) FROM readings GROUP BY mi, record_date HAVING COUNT(*) > 1;
> ```
> Resolve any hits before retrying `alembic upgrade head`.

### Start the stack

```bash
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend API: http://localhost:8500

Readings, billing statements, and leak detection data live in Postgres. Oracle wallet files are persisted in a bind-mounted `./data` directory (mapped to `/app/data` in the backend container), so they survive container restarts and rebuilds. Uploaded billing statement PDFs are only held in memory during import — the raw PDF is not stored, on disk or otherwise, after the statement's fields are extracted.

### Stop

```bash
docker compose down
```

### Rebuild after code changes

```bash
docker compose up --build
```

### Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Requires `TEST_DATABASE_URL` in `.env` (or exported) pointing at a dedicated Postgres database — see `.env.example`. It must hold no real data: every test run truncates all app tables in it. It needs its schema created the same way as the main database (`alembic upgrade head` against it) before the first run.

### Reset all data

```bash
docker compose down -v
```

> The `-v` flag only removes the `ollama_data` volume (the pulled local model). To reset app data: truncate the tables in Postgres (or drop and re-run `alembic upgrade head`) for readings/statements/leak sessions, and delete the `./data` directory yourself for Oracle wallets.

---

## Running in Kubernetes (production)

The production deployment runs on a self-hosted [k3s](https://k3s.io) cluster, managed entirely via GitOps with [Flux](https://fluxcd.io) — this repo *is* the source Flux reconciles against, so a merge to `master` is the deploy step. External access is via a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (no inbound router ports, no exposed home IP, TLS terminated at Cloudflare's edge).

### Prerequisites

- A k3s (or any Kubernetes) cluster with [Flux bootstrapped](https://fluxcd.io/flux/installation/bootstrap/) against this repo
- The [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) controller installed in-cluster (deployed via GitOps too, see `infrastructure/sealed-secrets/`)
- `kubeseal`, matching the in-cluster controller's version, for encrypting new/changed secret values before committing them

### Repo layout

| Path | Purpose |
|------|---------|
| `clusters/home/` | Flux `Kustomization` CRs — the entry point Flux reconciles, split into `infrastructure` (cluster-wide add-ons) and `apps` (this app), with `apps` depending on `infrastructure` |
| `infrastructure/sealed-secrets/` | Sealed Secrets controller, deployed via a Flux `HelmRelease` |
| `apps/water-meter/` | This app's namespace, `SealedSecret`s (`DATABASE_URL`, cloudflared tunnel credentials), and the `HelmRelease` that installs the chart below |
| `charts/water-meter/` | The Helm chart — backend, frontend, Ollama, and cloudflared, templated from `values.yaml` |

### Secrets

`DATABASE_URL` and the cloudflared tunnel credentials are committed to git as `SealedSecret`s (`apps/water-meter/secrets/`) — encrypted client-side with `kubeseal` against the controller's public cert, so only the cluster can decrypt them. To add or rotate one:

```bash
kubectl create secret generic <name> --dry-run=client -o yaml \
  --from-literal=KEY=value \
  | kubeseal --controller-namespace sealed-secrets --format yaml > apps/water-meter/secrets/<name>-sealedsecret.yaml
```

Oracle wallet files are **not** in Secrets — they stay on the backend's PVC, same as the bind-mounted `./data` directory in docker-compose. Moving them to Secrets (needed for true multi-replica backend scaling) is deferred to a future change.

### Cloudflare Tunnel

The tunnel uses the classic locally-managed mode (credentials file + `config.yaml`, both mounted into the `cloudflared` pod) rather than the token/Zero-Trust-dashboard mode, since Zero Trust requires a payment method on file even on the free tier. The tunnel's ingress routes the public hostname straight to the `frontend` service — so, same as local dev, only paths under `/api/` reach the backend (see `frontend/nginx.conf`). External health checks and API calls must go through `/api/`, not the bare path — `https://<hostname>/health` will return the React app's `index.html`, not JSON; use `https://<hostname>/api/health`.

### Configuring a deployment

Cluster-specific values (tunnel ID, public hostname, `ALLOWED_ORIGINS`) are set in `apps/water-meter/release.yaml`'s `spec.values`, which override `charts/water-meter/values.yaml`'s defaults. `ALLOWED_ORIGINS` must be the real `https://` tunnel hostname — Cloudflare terminates TLS, but the browser's `Origin` header on requests is still `https://`, so an `http://` value here reproduces the exact CORS bug this setup avoids.

### Deploying a change

Merging to `master` runs CI (tests, lint, build) and, once that passes, publishes updated backend/frontend images tagged `sha-<shortsha>`. From there:

- **Code changes** (backend/frontend): fully automatic, no manual step. CI's `update-image-tags` job runs after the image push, bumps `apps/water-meter/release.yaml`'s `image.backend.tag`/`image.frontend.tag` to the new `sha-<shortsha>`, and opens a second PR for that change. Since it's a mechanical follow-up (not a human-reviewed change), that PR auto-merges as soon as its own CI checks pass — so a normal merge to `master` produces a second, bot-authored PR in the history shortly after, and Flux picks up the resulting `HelmRelease` change on its own within a few minutes (or force it sooner, see below).
- **Chart/config changes** (anything under `charts/water-meter/`, `apps/water-meter/`, `infrastructure/`, or `clusters/`): Flux picks these up on its own within a few minutes, or force it sooner:
  ```bash
  flux reconcile helmrelease water-meter -n water-meter --with-source
  ```
  If the change is to the Helm chart itself (`charts/water-meter/templates/` or `values.yaml`), also bump the `version` in `charts/water-meter/Chart.yaml` — otherwise Flux won't pick up the change.

The `update-image-tags` job authenticates as a PAT (repo secret `ROLLOUT_PAT`, scoped to Contents + Pull requests read/write) rather than the default `GITHUB_TOKEN`, since GitHub doesn't trigger further workflow runs — including the required status checks the auto-merge waits on — for events caused by `GITHUB_TOKEN`. This also requires **Allow auto-merge** enabled in the repo's settings.

### Verifying a deployment

```bash
flux get helmreleases -A                        # water-meter should be Ready
kubectl get pods -n water-meter                  # backend/frontend/ollama/cloudflared all Running
curl https://<hostname>/api/health               # from outside the cluster's network — {"status":"ok"}
```

Then a full round-trip through the UI (e.g. add a reading) confirms `DATABASE_URL`, the `/api/` proxy, and CORS all work end to end.

---

## Configuration

### AI provider (required for AI chat; PDF import falls back to a local model)

Open **Settings → AI Provider Settings** in the app and paste your API key.

| Provider | Key type | Models used |
|----------|----------|-------------|
| Anthropic (default) | `sk-ant-...` | Claude for chat/NL2SQL, Voyage for embeddings |
| OpenAI | `sk-...` | GPT-4o for chat/NL2SQL, `text-embedding-3-small` for embeddings |

Keys are stored in your browser's localStorage and sent directly to the backend per-request. They are never written to disk or a database.

### Local model fallback (Ollama)

If no API key is configured, `POST /import-billing` automatically falls back to a local
model via [Ollama](https://ollama.com) instead of requiring a cloud key. This is
text-only extraction: the PDF's text layer is pulled out with `pypdf` and sent to the
model as a prompt. Scanned/image-only statements have no text layer, so those still
require a cloud API key. AI chat / NL2SQL (`ai_agent.py`, `oracle_ai.py`) is unaffected
and always requires a cloud key.

`docker compose up` runs Ollama as its own service and automatically pulls the default
model (`llama3.1`) on first run — no separate install needed, though the first pull
downloads several GB and takes a while. It runs CPU-only unless you add GPU passthrough
to the `ollama` service yourself.

| Env var | Default | Where |
|---------|---------|-------|
| `OLLAMA_BASE_URL` | `http://ollama:11434` (docker-compose) | Where the backend looks for Ollama |
| `OLLAMA_MODEL` | `llama3.1` | Model used for extraction, and what `ollama-pull` fetches in Docker |

---

## Using Daily Leak Detection

Open the **Leak Detection** tab in the sidebar. It always shows one **active session** — a clean workspace for the leak investigation currently in progress — plus a list of **archived sessions** from past investigations.

### 1. Import daily submeter readings

Take a daily photo of each submeter and transcribe it into a CSV (MVP is manual entry; an AI-assisted photo importer is planned for later):

```csv
mi,reading,record_date,unit
Unit1,100.0,2026-08-01,1
Unit2,50.0,2026-08-01,1
```

- `mi` — the household/submeter identifier
- `reading` — the cumulative meter reading
- `record_date` — `YYYY-MM-DD`
- `unit` — `1` if the meter reads in units of water (CCF), `0` if it reads in gallons (converted automatically at `1 unit = 748 gallons`)

Upload it under **Import Daily Submeter Readings**, review the preview (row count / errors), then **Confirm Import**. Repeat this daily to build up a run of readings.

### 2. Import daily main meter readings

Export a "range export" CSV from your main meter's AMI provider (columns: `Account_ID, Meter_ID, Meter_SN, Read_Time, Timezone, Read, Read_Unit, Read_Method, Flow_Time, Flow_Unit, Flow, Register`) and upload it under **Import Daily Main Meter Readings**. Readings must be in `CCF`; each row's `Flow` value is used directly as that period's main-meter delta.

### 3. Review the comparison

Once both sides have at least two days of data, the active session shows a line chart and a table comparing the **main meter flow** against the **summed submeter deltas** for each matching period. Any day where the submeter total exceeds the main meter's flow is highlighted red and marked **Potential Leak**.

### 4. Review the SFPUC / EyeOnWater rules

Below the comparison, a **Property Profile** panel shows the submeter household count and which volume-threshold window applies — **Standard** (48h) for fewer than 6 households, **Multi-Family** (72h) at 6 or more. The **Main Meter** card underneath evaluates three rules against the main meter's own readings only:

| Rule | Triggers when |
|------|---------------|
| **Continuous Flow** | Flow stays above a low threshold continuously for 24+ hours |
| **Volume Threshold** | Flow stays above a higher threshold continuously for 48h (72h if Multi-Family) |
| **Nighttime Ratio** | A night's usage (12am–5am) exceeds 2x the median of prior nights |

Each rule lists its alerts in a table; an alert still in effect as of the most recent reading is tagged **Ongoing** next to its end time, otherwise it's already resolved. Submeter readings are excluded from these rules since they're sparse, manually-transcribed entries that would never satisfy a continuous-coverage check.

### 5. Archive when the investigation is done

Click **Archive Session** and confirm. The active workspace resets to empty for the next investigation, while the archived session (and all its data) stays viewable under the **Archived Sessions** tab. Click **Restore** on an archived session to bring it back as the active workspace at any time — if the current active workspace has data of its own, it's archived first so nothing is lost.

---

## Project structure

```
water-meter/
├── backend/
│   ├── main.py              # FastAPI app, routes
│   ├── models.py            # SQLAlchemy models
│   ├── database.py          # DB engine and session (reads DATABASE_URL)
│   ├── alembic/              # Schema migrations
│   ├── ai_agent.py          # AI chat and PDF bill extraction
│   ├── csv_parser.py        # CSV import with format detection
│   ├── units.py             # Shared gallons↔units-of-water conversion
│   ├── leak_detection.py    # /leak/* endpoints (sessions, imports, analysis)
│   ├── leak_rules.py        # SFPUC/EyeOnWater rule engine (continuous flow, volume threshold, nighttime ratio, historical deviation)
│   ├── main_meter_csv.py    # AMI "range export" main meter CSV parser
│   ├── oracle_connection.py # Oracle connection pool + per-request creds
│   ├── oracle_ai.py         # /oracle/* endpoints (status, sync, NL2SQL, vector search)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx                        # Root layout, state, routing
│       └── components/
│           ├── Sidebar.jsx                # Collapsible dark sidebar
│           ├── DashboardSummary.jsx       # Stat cards + spike list
│           ├── UsageCharts.jsx            # Consumption charts
│           ├── MoneyLostChart.jsx         # $ gap between billed and summed household usage
│           ├── DataQuality.jsx            # Anomaly details
│           ├── StatementUpload.jsx        # PDF bill import
│           ├── StatementsList.jsx         # Billing statements table
│           ├── ImportWizard.jsx           # CSV import wizard
│           ├── ReadingTable.jsx           # Readings table with search + export
│           ├── LeakDetectionTool.jsx      # Daily Leak Detection tab (active/archived sessions)
│           ├── LeakSessionView.jsx        # Leak session comparison chart + table
│           ├── LeakDifferenceBarChart.jsx # Per-day submeter-vs-main-meter difference chart
│           ├── LeakRawDataTable.jsx       # Raw submeter / main meter reading tables
│           ├── LeakCsvImport.jsx          # Single-file CSV preview → confirm widget
│           ├── AIAssistant.jsx            # Chat / Ask Oracle / Semantic Search tabs
│           ├── ApiKeySettings.jsx         # AI provider key management
│           └── OracleSettings.jsx         # Oracle credential entry + sync actions
├── charts/water-meter/      # Helm chart for the k8s deployment (backend/frontend/ollama/cloudflared)
├── apps/water-meter/        # Flux HelmRelease, namespace, SealedSecrets for this app
├── infrastructure/          # Cluster-wide add-ons deployed via GitOps (Sealed Secrets controller)
├── clusters/home/           # Flux Kustomization CRs (the GitOps entry point)
├── docker-compose.yml
└── README.md
```

---

## API overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/readings` | List all meter readings |
| POST | `/readings` | Add a reading |
| DELETE | `/readings/{id}` | Delete a reading |
| GET | `/anomalies` | Spike detection: flags a household whose current daily usage rate is 2.5x+ its rolling 90-day baseline |
| GET | `/billing-statements` | List imported bills |
| POST | `/import-billing` | Upload and AI-extract a PDF bill (cloud key if set, else local Ollama) |
| POST | `/billing-statements` | Add a blank statement for manual entry |
| DELETE | `/billing-statements/{id}` | Delete a bill |
| GET | `/billing-verify` | Household sum vs bill verification |
| POST | `/import-csv/preview` | Preview a household meter reading CSV import, including duplicate/conflict counts |
| POST | `/import-csv/confirm` | Import a household meter reading CSV — skips exact duplicates, flags value conflicts for manual review, never overwrites |
| POST | `/readings/resolve-conflicts` | Bulk-apply imported values to existing rows flagged as conflicts by CSV import |
| GET | `/leak/sessions` | List all daily leak detection sessions |
| GET | `/leak/sessions/active` | Get (or create) the active leak detection session |
| GET | `/leak/sessions/{id}/analysis` | Per-day main-meter-vs-submeter comparison and leak flags, plus SFPUC/EyeOnWater rule results for the main meter |
| GET | `/leak/sessions/{id}/submeter-readings` | List raw submeter readings for a session |
| GET | `/leak/sessions/{id}/main-meter-readings` | List raw main-meter readings for a session |
| DELETE | `/leak/sessions/{id}` | Delete an archived session and its readings (the active session can't be deleted) |
| POST | `/leak/submeter/import/preview` | Preview a daily submeter CSV |
| POST | `/leak/submeter/import/confirm` | Import a daily submeter CSV into the active session |
| DELETE | `/leak/submeter/{id}` | Delete a single submeter reading |
| DELETE | `/leak/submeter` | Bulk-delete submeter readings by id |
| POST | `/leak/main-meter/import/preview` | Preview a daily main meter (AMI) CSV |
| POST | `/leak/main-meter/import/confirm` | Import a daily main meter CSV into the active session |
| DELETE | `/leak/main-meter/{id}` | Delete a single main-meter reading |
| DELETE | `/leak/main-meter` | Bulk-delete main-meter readings by id |
| POST | `/leak/sessions/{id}/archive` | Archive the active session, starting a fresh workspace |
| POST | `/leak/sessions/{id}/restore` | Restore an archived session as the active workspace |
| POST | `/ai/ask` | Chat with AI about your data |
| POST | `/oracle/wallet/parse` | Upload an Oracle wallet zip; returns available service names for profile creation |
| GET | `/oracle/profiles` | List saved Oracle connection profiles (passwords excluded) |
| POST | `/oracle/profiles` | Create a connection profile from a previously parsed wallet |
| DELETE | `/oracle/profiles/{id}` | Delete a connection profile and its wallet files |
| GET | `/oracle/status` | Oracle connection health check |
| POST | `/oracle/init` | Create Oracle tables |
| POST | `/oracle/sync` | Sync Postgres → Oracle |
| POST | `/oracle/embed-sync` | Generate and store embeddings |
| POST | `/oracle/vector-search` | Semantic similarity search |
| POST | `/oracle/ask` | NL2SQL query against Oracle |

AI endpoints accept `X-Api-Key` and `X-Api-Provider`. Oracle endpoints (except wallet/profile management) accept `X-Oracle-Profile-Id` to select which saved connection profile to use.
