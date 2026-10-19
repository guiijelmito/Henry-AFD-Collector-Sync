# Henry AFD Collector & Sync

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)](https://playwright.dev/python/)
[![Status](https://img.shields.io/badge/Status-In%20Development-yellow.svg)]()

Automated Python service that extracts **AFD (Arquivo Fonte de Dados)** files from Henry electronic time clocks (Super Fácil RO2 / Prisma Super Fácil R2) through Playwright and uploads them to the central panel.

---

## 🚀 Key Features

- **Resilient Web Automation:** Uses Playwright to interact with Henry's web panel, handling authentication, sessions, and precise element selectors.
- **Weekly date/time collection:** Each Friday, downloads records from Monday at 00:00 through the current time. NSRs remain part of the AFD records but are not used as collection cursors.
- **Audit schedule (`estado_ponto.json`):** Keeps an independent next permitted audit time for each unit and only collects/uploads on Fridays after that time.
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

Ensure `estado_ponto.json` exists in the root directory with the next audit time for each unit:

```json
{
  "next_audit_at_v1": "2000-01-01T00:00:00-03:00",
  "next_audit_at_v2": "2000-01-01T00:00:00-03:00"
}
```

V1 and V2 have independent schedules. Collection and upload are skipped on every
day except Friday and until the saved audit time is due. A due Friday downloads
Monday 00:00 through the current date and time, uploads the AFD, then schedules
the next audit seven days later. A missing state file makes the first Friday
eligible. The old `next_advance_at_v1/v2` and V1 `next_date` schedule keys are
read during migration; the old NSR cursor fields are discarded when an upload
is recorded. No NSR cursor is required for the new date/time filters.

Date/time filters use `lblDataI` and `lblDataF` on both clocks. The V1 panel
uses the `communication` filter view and download action `subCompD(5, 8, 2)`;
the V2 panel uses `menuItem2` and `downloadData(1,32,2)`.

---

## Usage

Run the main automation script:

```bash
python main.py
```

On Windows, `executar.bat` runs this command from the project directory and returns
the Python process exit code.

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
├── afd_downloads/         # Directory where downloaded AFD text files are stored
├── .env                   # Sensitive credentials and URLs (git-ignored)
├── .gitignore             # Excludes venv, .env, state files, and downloads
├── config.py              # Configuration loader and environment variables bindings
├── state_store.py         # Validated, atomic JSON state persistence for both clocks
├── estado_ponto.json      # Independent next audit times for V1 and V2
├── extract_afc_v1.py      # Playwright automation script for Unit V1 (Local)
├── extract_afc_v2.py      # Playwright automation script for Unit V2 (External via Tailscale)
├── cloud.py               # Synchronization and automated web server upload module
├── main.py                # Unified central orchestrator for the complete pipeline
├── executar.bat           # Windows wrapper script for automated background task scheduling
├── tests/                 # State integrity and weekly V1 cursor tests
├── pyproject.toml         # Ruff, pytest, and coverage configuration
├── requirements-dev.txt   # Pinned quality and security tools
└── README.md              # Official project documentation
```

---

## ⚖️ License

This project is proprietary software developed for **Verth Tecnologia**.
