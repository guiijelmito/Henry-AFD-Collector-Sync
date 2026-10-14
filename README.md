# Henry AFD Collector & Sync

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)](https://playwright.dev/python/)
[![Status](https://img.shields.io/badge/Status-In%20Development-yellow.svg)]()

Automated Python service designed to extract **AFD (Arquivo Fonte de Dados)** files from Henry Electronic Time Clocks (Super Fácil RO2 / Prisma Super Fácil R2) via Playwright web automation, featuring dynamic NSR (Sequential Number of Record) state tracking and automated cloud/PHP backend synchronization.

---

## 🚀 Key Features

- **Resilient Web Automation:** Uses Playwright to interact with Henry's web panel, handling authentication, sessions, and precise element selectors.
- **Dynamic NSR State Management (`estado_ponto.json`):** Automatically calculates batch ranges per execution cycle, ensuring continuous data collection without gaps or overlaps.
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

Ensure `estado_ponto.json` exists in the root directory with your initial NSR pointer:

```json
{
  "last_nsr_v1": "000045076",
  "last_nsr_v2": "000001153",
  "next_date": "2026-01-01"
}
```

The V1 cursor advances only when `next_date` is more than seven days in the past.
The V2 cursor advances after its download is saved. A missing state file starts from
the configured defaults; malformed JSON or a nonnumeric cursor stops collection so
the automation cannot silently reset to an earlier NSR. The legacy `ultimo_nsr`
field is still read as the V1 cursor.

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
python -m pip_audit --local
```

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
├── estado_ponto.json      # Dynamic state tracker for the last processed NSR
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
