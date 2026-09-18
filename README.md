# Henry AFD Collector & Sync

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)](https://playwright.dev/python/)
[![Status](https://img.shields.io/badge/Status-In%20Development-yellow.svg)]()

Automated Python service designed to extract **AFD (Arquivo Fonte de Dados)** files from Henry Electronic Time Clocks (Super Fácil RO2 / Prisma Super Fácil R2) via Playwright web automation, featuring dynamic NSR (Sequential Number of Record) state tracking and automated cloud/PHP backend synchronization.

---

## Key Features

- **Resilient Web Automation:** Uses Playwright to interact with Henry's web panel, handling authentication, sessions, and precise element selectors.
- **Dynamic NSR State Management (`estado_ponto.json`):** Automatically calculates batch ranges per execution cycle, ensuring continuous data collection without gaps or overlaps.
- **Secure Configuration:** Isolates sensitive credentials and device IPs using environment variables (`.env`).
- **Structured Storage:** Automatically saves extracted AFD files into a dedicated target directory (`afd_downloads/`).
- **Backend Integration:** Designed to seamlessly feed extracted data into a PHP backend server and cloud infrastructure.

---

## Tech Stack

- **Language:** Python 3.10+
- **Automation:** Playwright for Python
- **Environment Management:** `python-dotenv`
- **Persistence:** JSON-based state tracking

---

## Installation & Setup

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
pip install playwright python-dotenv
playwright install chromium
```

### 4. Configure environment variables

Create a `.env` file in the root directory based on your clock settings:

```env
IP_V1=192.168.X.XXX
USUARIO_V1=rep
SENHA_V1=your_password_here
HEADLESS_MODE=False
SLOW_MO_MS=500
```

### 5. Initialize state file

Ensure `estado_ponto.json` exists in the root directory with your initial NSR pointer:

```json
{
  "ultimo_nsr": "000044930"
}
```

---

## Usage

Run the main automation script:

```bash
python extract_afc_V1.py
```

---

## Project Structure

```
├── afd_downloads/       # Directory where downloaded AFD text files are stored
├── .env                 # Sensitive credentials (git-ignored)
├── .gitignore            # Excludes venv, .env, state files, and downloads
├── config.py             # Configuration loader and environment bindings
├── estado_ponto.json        # Dynamic state tracker for the last processed NSR
├── extract_afc_V1.py     # Main Playwright automation script
└── README.md             # Project documentation
```

---

## License

This project is proprietary software developed for **Verth Tecnologia**.
