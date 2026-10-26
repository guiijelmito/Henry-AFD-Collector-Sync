# Henry AFD Collector & Sync

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)](https://playwright.dev/python/)
[![Status](https://img.shields.io/badge/Status-In%20Development-yellow.svg)]()

Automated Python service that extracts **AFD (Arquivo Fonte de Dados)** files from Henry electronic time clocks (Super Fácil RO2 / Prisma Super Fácil R2) through Playwright and uploads them to the central panel.

---

## 🚀 Key Features

- **Resilient Web Automation:** Uses Playwright to interact with Henry's web panel, handling authentication, sessions, and precise element selectors.
- **Closed-week collection:** Downloads each finished week, Sunday 00:00 to Saturday 23:59, one AFD per week. Missed weeks are recovered in order (up to `MAX_SEMANAS_POR_EXECUCAO`, default 4, per run). NSRs remain part of the AFD records but are not used as collection cursors.
- **Schedule (`estado_ponto.json`):** Keeps, per unit, the last week sent and the next permitted collection time (Sunday 00:05).
- **Secure Configuration:** Isolates sensitive credentials and device IPs using environment variables (`.env`).
- **Structured Storage:** Automatically saves extracted AFD files into a dedicated target directory (`afd_downloads/`).
- **Backend Integration:** Designed to seamlessly feed extracted data into a PHP backend server and cloud infrastructure.

---

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **Automation:** Playwright for Python
- **Environment Management:** `python-dotenv`
- **Persistence:** JSON-based state tracking

---

## ⚙️ Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/henry-afd-collector.git
cd henry-afd-collector
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and set the panel credentials, both clock addresses,
and the usernames and passwords. The V2 address must be reachable over Tailscale.
The default download and log directories are created under the project folder.
Set `DIRETORIO_BASE` or `DIRETORIO_DOWNLOADS` only when you need a different location.

```env
copy .env.example .env
```

### 5. Initialize state file

`estado_ponto.json` keeps, per unit, the Sunday of the last week sent and when the
next collection is allowed:

```json
{
  "ultima_semana_v1": "2026-10-11",
  "next_audit_at_v1": "2026-10-25T00:05-03:00",
  "ultima_semana_v2": "2026-10-11",
  "next_audit_at_v2": "2026-10-25T00:05-03:00"
}
```

A unit is collected at or after its `next_audit_at`, on any day. Each run sends the
closed weeks after `ultima_semana_v1/v2` (Sunday 00:00 to Saturday 23:59), oldest
first; a week is only closed after Saturday 23:59. After each week is uploaded,
`ultima_semana` becomes that week and `next_audit_at` becomes the Sunday 00:05 right
after the following week ends. Without state, the first run sends the last closed
week. Weeks without punches (holidays, vacations) are still uploaded. The old
`next_advance_at_v1/v2` and V1 `next_date` keys are read during migration, and
`collected_until_v1/v2` is discarded.

To send one week again (for example, after a panel problem) without changing the
state, pass any date inside it:

```bash
python main.py --semana 2026-10-18
```

Date/time filters use `lblDataI` and `lblDataF` on both clocks. The V1 panel
uses the `communication` filter view and download action `subCompD(5, 8, 2)`;
the V2 panel uses `menuItem2` and `downloadData(1,32,2)`.

## Docker (DigitalOcean Droplet)

The image packages the application, Python dependencies, and the matching
Playwright Chromium runtime. Compose runs the scheduled pipeline as a one-shot
container; the Droplet's host scheduler can start it daily. The container
uses the host network so it can use routes configured on the Droplet, including
the V2 Tailscale route. Both clock addresses must be reachable from the host.

Create a runtime environment file and persistent data directory on the host:

```bash
cp .env.example .env
mkdir -p data
```

Fill `.env` with real credentials and reachable clock addresses, then build and
run the scheduled pipeline:

```bash
docker compose build
docker compose run --rm afd-collector
```

The `data/` directory is mounted at `/data` and retains `estado_ponto.json` and
logs between runs. Downloaded AFDs are written under `/tmp` inside the container;
with `--rm`, the container and those temporary files are removed after the run.
The `.env` file is supplied at runtime and excluded from the image build context.
Run this Compose configuration on Linux for the Droplet deployment because it
uses host networking. Install and connect Tailscale on the Droplet host before
expecting V2 to be reachable. This command runs the production schedule gate;
before `next_audit_at`, it exits without collecting or uploading.

---

## Usage

Run the main automation script:

```bash
python main.py
```

On Windows, `executar.bat` runs this command from the project directory and returns
the Python process exit code.

### Retries, reports and alerts

Download and upload are retried (`TENTATIVAS`, default 3) with a growing wait
(`ESPERA_ENTRE_TENTATIVAS_S`). Every run that reaches a due unit writes a report to
`logs/relatorios/` as JSON and PDF: status per unit, what went wrong in plain
language, what to do next, warnings and failure screenshots. If configured in `.env`,
the summary and the PDF are sent via Telegram, with SMTP e-mail as a fallback. The
exit code is `1` when any unit failed, so the scheduler shows the failure.

### Scheduling on Windows

Run once, in an administrator PowerShell, from the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\agendar_tarefa.ps1
```

The task runs every day at 00:05. Before `next_audit_at` it exits in seconds without
opening the browser. If Sunday's run fails or the PC is off, the next day's run sends
the weeks still pending, in order.

## Development checks

Install the pinned development tools and run the unit tests, branch coverage, lint,
and formatting checks:

```bash
pip install -r requirements-dev.txt
python -m pytest --cov --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m pip_audit --local --strict
```

Pytest writes temporary files to `.tmp/pytest-basetemp`, avoiding Windows system
temporary folders with restricted permissions. The folder is disposable and is
cleared by pytest between runs. Ruff keeps its cache under `.tmp/ruff_cache`.

The dependency audit inspects the active virtual environment, including installed
transitive dependencies. Activate the environment populated with
`requirements-dev.txt` before running it. `pip-audit` needs network access to query
the vulnerability service; `--strict` makes dependency collection failures fail
the command instead of silently producing an incomplete report.

Coverage currently measures the isolated state persistence module; the Playwright
flows still need browser and panel integration tests before the project can claim
end-to-end coverage.

---

## 🗂️ Project Structure

```
├── src/ponto_eletronico/
│   ├── pipeline.py        # Orchestrates V1 and V2: window, retries, report, alert, exit code
│   ├── state_store.py     # estado_ponto.json: last week sent and next collection time per unit, atomic writes
│   ├── afd_validation.py  # Date/time filter input and AFD range validation
│   ├── extractors/        # Playwright automation for the V1 and V2 clocks
│   ├── cloud.py           # Upload to the central panel
│   ├── relatorio.py       # JSON/PDF run report
│   ├── alertas.py         # Telegram and e-mail alerts
│   ├── config.py          # Environment settings
│   └── logging_config.py  # Console/file logging and screenshots
├── scripts/
│   ├── executar.bat       # Windows wrapper used by the scheduler
│   └── agendar_tarefa.ps1 # Registers the daily task in Task Scheduler
├── tests/unit/            # Tests that run without clocks or panel
├── tests/integration/     # Tests that need the real infrastructure
├── config/                # Example state file
├── Dockerfile, compose.yaml
├── main.py                # Entry point (python main.py)
└── executar.bat           # Shortcut to scripts/executar.bat
```

---

## ⚖️ License

This project is proprietary software developed for **Verth Tecnologia**.
