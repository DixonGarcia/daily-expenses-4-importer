# 🏦 Daily Expenses 4 Importer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Playwright](https://img.shields.io/badge/tested%20with-Playwright-green.svg)](https://playwright.dev/)

**Daily Expenses 4 Importer** is a modular CLI tool that automates importing bank statements and credit card movements directly into the **[Daily Expenses 4](https://dailyexpenses4.com)** web app via Playwright browser automation.

---

## ✨ Features

- **Automated Web Automation**: Automatically logs in and loads movements (Expenses and Transfers) into Daily Expenses 4 without manual data entry.
- **Pluggable Parser Architecture**: Easily parse CSV, Excel (`.xls`, `.xlsx`), and custom bank formats.
- **Built-in Parsers**:
  - **Generic CSV**: Auto-detects column headers for Date, Description, Debit/Credit/Amount.
  - **Banesco Panamá TDC**: Parses credit card statements in Excel and CSV with merchant cleanup.
- **Interactive Classifier & Rule Engine**:
  - Remembers merchant-to-category associations in a local SQLite database (`data/importer.db`).
  - Auto-suggests saved rules for future imports.
- **Transfer Support**: Seamlessly loads account-to-account transfers (such as credit card payments from checking accounts).
- **Anti-Duplicate Tracking**: Tracks processed transaction references to prevent importing duplicate expenses.
- **Audit Logging**: Structured execution logs written to `tmp/importer.log`.

---

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/DixonGarcia/daily-expenses-4-importer.git
cd daily-expenses-4-importer

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and CLI
pip install -e .
playwright install chromium
```

### 2. Configuration

Copy the example configuration file:

```bash
cp data/config.toml.example data/config.toml
```

Edit `data/config.toml` to match your account names in Daily Expenses 4.

### 3. Usage

Import any bank statement or credit card file:

```bash
# Basic import with auto-detected parser
daily-expenses-importer -i /path/to/statement.csv

# Import into a specific account and watch the browser window in real-time
daily-expenses-importer -i /path/to/credit_card.xls -a "TDC - Banesco" -v

# Dry run (test classification and summary without loading into web app)
daily-expenses-importer -i /path/to/statement.csv --dry-run
```

#### CLI Options:
- `-i, --input <path>`: Path to the bank statement file (**required**).
- `-a, --account <name>`: Target account name in Daily Expenses 4.
- `-v, --visible`: Open the browser window during automation.
- `-d, --dry-run`: Parse and show the classification summary without uploading.
- `-c, --config <path>`: Custom configuration file path (default: `data/config.toml`).

---

## 🛠 Adding a Custom Bank Parser

To add support for your bank, create a parser class inheriting from `BaseParser`:

```python
from pathlib import Path
from daily_expenses_importer.parsers.base import BaseParser, NormalizedTransaction, TransactionType

class MyBankParser(BaseParser):
    @property
    def name(self) -> str:
        return "my_bank"

    def supports(self, file_path: Path, sample_bytes: bytes) -> bool:
        return "MY_BANK_IDENTIFIER" in sample_bytes.decode("utf-8", errors="ignore")

    def parse(self, file_path: Path) -> list[NormalizedTransaction]:
        # Parse your bank format and yield NormalizedTransaction objects
        ...
```

Register it in `daily_expenses_importer/parsers/__init__.py` and it will be auto-detected!

---

## 🧪 Testing

Run the test suite:

```bash
pytest tests/ -v
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
