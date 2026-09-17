# 🏦 Daily Expenses 4 Importer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Playwright](https://img.shields.io/badge/tested%20with-Playwright-green.svg)](https://playwright.dev/)

**Daily Expenses 4 Importer** is a modular, resilient CLI tool that automates importing bank statements, spreadsheets, and custom CSV templates directly into the **[Daily Expenses 4](https://dailyexpenses4.com)** web app via Playwright browser automation.

---

## ✨ Features

- 🤖 **Resilient Web Automation**: Automatically logs in and loads movements (Expenses, Incomes, Transfers) into Daily Expenses 4 with self-healing error recovery (no cascading failures).
- 📄 **Ready-to-use Excel & CSV Templates**: Generate pre-formatted `template.xlsx` (with setup sheet & dropdown lists) and `template.csv` with a single command (`--template`).
- 🌐 **Multi-Language Calendar Support**: Seamlessly parses and navigates Angular datepicker headers across Spanish, English, Portuguese, French, German, and Italian.
- 🔁 **Fault-Tolerant Retry Loop**: If any movements fail during upload (e.g. temporary network hiccups or UI timeouts), the CLI shows exact error reasons, offers an immediate 1-click retry, and allows saving any remaining failures to `failed_movements.csv` for later.
- 🧩 **Pluggable Parser Architecture**: Easily parse custom CSV, Excel (`.xls`, `.xlsx`), and bank statement formats.
  - **Generic Excel (`.xlsx`)**: Reads multi-sheet workbooks, setup templates, and data sheets with automatic header detection.
  - **Generic CSV / TSV**: Auto-detects column headers for Date/Time, Description, Category, Amount, Type (expense/income/transfer), and Account.
- 🏷️ **Smart Classification**: Direct recognition of categories and accounts from the spreadsheet, with interactive prompts and a local SQLite rule database (`data/importer.db`) for unclassified items.
- 🛡️ **Anti-Duplicate Tracking**: Tracks processed transaction references in SQLite to prevent duplicate entries.
- 📜 **Audit Logging**: Complete execution audit logs in `tmp/importer.log`.

---

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/DixonGarcia/daily-expenses-4-importer.git
cd daily-expenses-4-importer

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and CLI in editable mode
pip install -e .
playwright install chromium
```

### 2. Configuration

Copy the example configuration file:

```bash
cp data/config.toml.example data/config.toml
```

Edit `data/config.toml` with your default account names in Daily Expenses 4.

---

## 📝 Usage

### Option A: Using the interactive `template.xlsx` or `template.csv`

Generate fresh template files:

```bash
daily-expenses-importer --template
```

This creates:
- **`template.xlsx`**: Excel workbook with an **Instructions & Setup** sheet (to list your accounts & categories) and a **Movements** sheet with dynamic dropdown lists for Account, Category, and Type.
- **`template.csv`**: Equivalent plain text CSV file.

Example data format:

```csv
date,description,category,amount,type,account
2026-09-15 14:30:00,Supermarket Groceries,Groceries,45.50,expense,Checking Account
2026-09-16 09:15:00,Monthly Salary Deposit,Income,1500.00,income,Checking Account
2026-09-17 18:20:00,Credit Card Payment,Transfer,120.00,transfer,Checking Account -> Credit Card
2026-09-18 11:45:00,Pharmacy & Medicine,Healthcare,12.30,expense,Checking Account
2026-09-19 20:30:00,Restaurant Dinner,Dining,34.00,expense,Credit Card
```

Import your file:

```bash
daily-expenses-importer -i template.xlsx
# or
daily-expenses-importer -i template.csv
```

### Option B: Importing bank statements or custom CSV files

```bash
# Preview transactions and classifications without uploading (dry run)
daily-expenses-importer -i statement.csv --dry-run

# Import into a specific account and watch the browser window in real-time
daily-expenses-importer -i statement.csv -a "Checking Account" -v
```

### CLI Options

| Flag | Description |
|---|---|
| `-i, --input <path>` | Path to statement or spreadsheet file (**required** unless `--template`). |
| `-t, --template` | Generate standard `template.xlsx` and `template.csv` in the current directory. |
| `-a, --account <name>` | Target account name in Daily Expenses 4 (overrides config default). |
| `-v, --visible` | Open visible browser window during automation (default: headless). |
| `-d, --dry-run` | Parse and preview movements summary table without uploading. |
| `-c, --config <path>` | Custom configuration file path (default: `data/config.toml`). |

---

## 🛠 Adding a Custom Bank Parser

To add custom statement support for your bank, create a parser class inheriting from `BaseParser`:

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
