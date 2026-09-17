"""Template generator for Daily Expenses 4 Importer.

Generates:
1. `template.xlsx`: Multi-sheet Excel workbook with setup instructions, custom accounts/categories,
   and dynamic dropdown validations on the movements sheet.
2. `template.csv`: Standard plain text CSV with date and time included.
"""

from __future__ import annotations

from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation

DEFAULT_ACCOUNTS = [
    "Checking Account",
    "Credit Card",
    "Cash",
    "Savings",
    "Payroll",
]

DEFAULT_CATEGORIES = [
    "Bills",
    "Clothing",
    "Dining",
    "Education",
    "Entertainment",
    "Fuel",
    "Groceries",
    "Healthcare",
    "Home",
    "Income",
    "Insurance",
    "Kids",
    "Merchandise",
    "Other",
    "Personal",
    "Pets",
    "Subscriptions",
    "Tips",
    "Toll",
    "Transfer",
    "Transportation",
    "Travel",
    "Utilities",
    "Vehicle",
]

TEMPLATE_CSV_CONTENT = """date,description,category,amount,type,account
2026-09-15 14:30:00,Supermarket Groceries,Groceries,45.50,expense,Checking Account
2026-09-16 09:15:00,Monthly Salary Deposit,Income,1500.00,income,Checking Account
2026-09-17 18:20:00,Credit Card Payment,Transfer,120.00,transfer,Checking Account -> Credit Card
2026-09-18 11:45:00,Pharmacy & Medicine,Healthcare,12.30,expense,Checking Account
2026-09-19 20:30:00,Restaurant Dinner,Dining,34.00,expense,Credit Card
"""


def generate_excel_template(dest_path: Path = Path("template.xlsx")) -> Path:
    """Generate a rich, multi-sheet template.xlsx with dropdown validations and setup instructions."""
    wb = openpyxl.Workbook()

    # Style definitions
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Calibri", size=14, bold=True, color="1F4E79")
    subtitle_font = Font(name="Calibri", size=11, italic=True, color="595959")
    section_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    section_font = Font(name="Calibri", size=11, bold=True, color="1F4E79")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # -------------------------------------------------------------
    # SHEET 1: Setup (Instructions & Accounts/Categories)
    # -------------------------------------------------------------
    ws_setup = wb.active
    ws_setup.title = "Setup"

    ws_setup["B2"] = "🏦 Daily Expenses 4 Importer — Setup & Accounts"
    ws_setup["B2"].font = title_font

    ws_setup["B3"] = "Instructions:"
    ws_setup["B3"].font = Font(name="Calibri", size=11, bold=True)
    instructions = [
        "1. Write your exact Daily Expenses 4 Account names in Column B (e.g. 'Checking Account', 'Credit Card', 'Cash').",
        "2. Review or customize your Categories in Column D.",
        "3. Go to the 'Movements' sheet and enter your transactions using the dropdown lists.",
        "4. In the 'Date & Time' column, use YYYY-MM-DD HH:MM:SS format (e.g. 2026-09-15 14:30:00).",
        "5. To import, run: daily-expenses-importer -i template.xlsx",
    ]
    for i, inst in enumerate(instructions, 4):
        ws_setup[f"B{i}"] = inst
        ws_setup[f"B{i}"].font = subtitle_font

    # Tables Header
    ws_setup["B10"] = "Accounts"
    ws_setup["B10"].font = section_font
    ws_setup["B10"].fill = section_fill
    ws_setup["B10"].alignment = Alignment(horizontal="center")

    ws_setup["D10"] = "Categories"
    ws_setup["D10"].font = section_font
    ws_setup["D10"].fill = section_fill
    ws_setup["D10"].alignment = Alignment(horizontal="center")

    # Populate default accounts
    for idx, acc in enumerate(DEFAULT_ACCOUNTS, 11):
        cell = ws_setup[f"B{idx}"]
        cell.value = acc
        cell.border = thin_border

    # Populate default categories
    for idx, cat in enumerate(DEFAULT_CATEGORIES, 11):
        cell = ws_setup[f"D{idx}"]
        cell.value = cat
        cell.border = thin_border

    ws_setup.column_dimensions["A"].width = 4
    ws_setup.column_dimensions["B"].width = 30
    ws_setup.column_dimensions["C"].width = 6
    ws_setup.column_dimensions["D"].width = 30

    # -------------------------------------------------------------
    # SHEET 2: Movements (Transactions)
    # -------------------------------------------------------------
    ws_data = wb.create_sheet(title="Movements")

    headers = [
        "Date & Time",
        "Description",
        "Category",
        "Amount",
        "Type",
        "Account",
    ]

    for col_num, h_text in enumerate(headers, 1):
        cell = ws_data.cell(row=1, column=col_num, value=h_text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    sample_rows = [
        ("2026-09-15 14:30:00", "Supermarket Groceries", "Groceries", 45.50, "Expense", "Checking Account"),
        ("2026-09-16 09:15:00", "Monthly Salary Deposit", "Income", 1500.00, "Income", "Checking Account"),
        ("2026-09-17 18:20:00", "Credit Card Payment", "Transfer", 120.00, "Transfer", "Checking Account -> Credit Card"),
        ("2026-09-18 11:45:00", "Pharmacy & Medicine", "Healthcare", 12.30, "Expense", "Checking Account"),
        ("2026-09-19 20:30:00", "Restaurant Dinner", "Dining", 34.00, "Expense", "Credit Card"),
    ]

    for row_idx, row_data in enumerate(sample_rows, 2):
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_data.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border
            if col_idx == 4:
                cell.number_format = "$#,##0.00"

    # Data Validations (Dropdowns)
    # 1. Type Validation
    dv_type = DataValidation(type="list", formula1='"Expense,Income,Transfer"', allow_blank=True)
    dv_type.error = "Select a valid movement type (Expense, Income, Transfer)"
    dv_type.errorTitle = "Invalid Type"
    ws_data.add_data_validation(dv_type)
    dv_type.add("E2:E500")

    # 2. Category Validation referencing Sheet 1
    dv_cat = DataValidation(type="list", formula1="=Setup!$D$11:$D$40", allow_blank=True)
    dv_cat.error = "Select a category from the list or add it in the Setup sheet"
    dv_cat.errorTitle = "Invalid Category"
    ws_data.add_data_validation(dv_cat)
    dv_cat.add("C2:C500")

    # 3. Account Validation referencing Sheet 1
    dv_acc = DataValidation(type="list", formula1="=Setup!$B$11:$B$30", allow_blank=True)
    dv_acc.error = "Select an account from the list or add it in the Setup sheet"
    dv_acc.errorTitle = "Invalid Account"
    ws_data.add_data_validation(dv_acc)
    dv_acc.add("F2:F500")

    # Column widths
    ws_data.column_dimensions["A"].width = 24
    ws_data.column_dimensions["B"].width = 32
    ws_data.column_dimensions["C"].width = 22
    ws_data.column_dimensions["D"].width = 14
    ws_data.column_dimensions["E"].width = 16
    ws_data.column_dimensions["F"].width = 35

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest_path)
    wb.close()
    return dest_path


def generate_csv_template(dest_path: Path = Path("template.csv")) -> Path:
    """Generate a standard template.csv file with date and time."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(TEMPLATE_CSV_CONTENT, encoding="utf-8")
    return dest_path
