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

Create a `.env` file in the root directory based on your clock settings:

```env
SERVER_URL=https://example.invalid
SERVER_USER=your_server_user
SERVER_PASSWORD=replace_me
IP_V1=192.0.2.10
USUARIO_V1=your_clock_user
SENHA_V1=replace_me
IP_V2=192.0.2.20
USUARIO_V2=your_clock_user
SENHA_V2=replace_me
HEADLESS_MODE=true
```

See `.env.example` for the optional settings (batch size, retries, Telegram and e-mail alerts).

### 5. Initialize state file

`estado_ponto.json` in the root directory keeps, per unit, the last NSR already sent and the
date from which the next collection is allowed:

```json
{
  "last_nsr_v1": "000045076",
  "last_nsr_v2": "000001153",
  "next_date_v1": "2026-10-30",
  "next_date_v2": "2026-10-30"
}
```

A unit is collected on or after its `next_date`. After a successful upload the NSR moves to the
last record actually downloaded and `next_date` moves forward in 7-day steps, keeping the weekday.
The older shared `next_date` key is still read as the default for both units.

---

## Usage

Run the main automation script:

```bash
python main.py            # collects only the units whose next_date has arrived
python main.py --forcar   # collects now, ignoring next_date
```

Each run that collects something writes a report to `logs/relatorios/` (JSON and PDF) and,
if configured, sends the summary and the PDF via Telegram (or e-mail as a fallback).
The exit code is `1` when any unit failed, so the Windows Task Scheduler shows the failure.

### Scheduling (Windows)

Run once, in an administrator PowerShell, from the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\agendar_tarefa.ps1
```

The task runs every day at 00:00. On days before `next_date` it exits in seconds without opening
the browser, so a Friday missed because the PC was off, or a failed run, is retried the next night.

---

## 🗂️ Project Structure

```
├── src/ponto_eletronico/  # Aplicação e regras de negócio
│   ├── config.py
│   ├── pipeline.py        # Coleta por unidade, tentativas e código de saída
│   ├── estado.py          # estado_ponto.json: último NSR e janela de coleta
│   ├── afd.py             # Leitura dos NSRs do arquivo AFD
│   ├── relatorio.py       # Relatório JSON/PDF de cada execução
│   ├── alertas.py         # Telegram e e-mail
│   ├── cloud.py
│   ├── logging_config.py
│   ├── path_utils.py
│   └── extractors/        # Automações Henry V1 e V2
├── config/                # Exemplos de configuração
├── scripts/               # Execução e manutenção
├── tests/unit/            # Testes sem acessar relógios nem servidor
├── tests/integration/     # Testes que dependem da infraestrutura
├── main.py                # Atalho compatível para iniciar o pipeline
├── executar.bat           # Atalho para o agendador do Windows
└── README.md
```

---

## ⚖️ License

This project is proprietary software developed for **Verth Tecnologia**.
