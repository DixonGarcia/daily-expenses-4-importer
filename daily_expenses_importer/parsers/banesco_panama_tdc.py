"""Parser for Banesco Panamá Credit Card (TDC) statements in Excel (.xls/.xlsx) and CSV formats."""

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from daily_expenses_importer.parsers.base import BaseParser, NormalizedTransaction, TransactionType


class BanescoPanamaTdcParser(BaseParser):
    """Parser for Banesco Panamá Credit Card transaction statements."""

    @property
    def name(self) -> str:
        return "banesco_panama_tdc"

    def supports(self, file_path: Path, sample_bytes: bytes) -> bool:
        ext = file_path.suffix.lower()
        if ext in {".xls", ".xlsx"}:
            try:
                with zipfile.ZipFile(file_path, "r") as z:
                    return "xl/worksheets/sheet1.xml" in z.namelist()
            except Exception:
                return False
        elif ext == ".csv":
            sample_text = sample_bytes.decode("utf-8", errors="ignore")[:2048]
            return "FECHA TRANSACCIÓN" in sample_text or "MOVIMIENTOS DE TARJETA" in sample_text
        return False

    def parse(self, file_path: Path) -> list[NormalizedTransaction]:
        ext = file_path.suffix.lower()
        if ext in {".xls", ".xlsx"}:
            raw_rows = self._read_excel_rows(file_path)
        else:
            raw_rows = self._read_csv_rows(file_path)

        transactions = []
        for idx, (dt_str, desc_str, amount_str) in enumerate(raw_rows, 1):
            tx = self._parse_transaction_row(dt_str, desc_str, amount_str, fallback_idx=idx)
            if tx:
                transactions.append(tx)

        # Sort chronologically (oldest to newest)
        return sorted(transactions, key=lambda t: t.date)

    def _read_excel_rows(self, file_path: Path) -> list[tuple[str, str, str]]:
        rows = []
        with zipfile.ZipFile(file_path, "r") as z:
            shared_strings = []
            if "xl/sharedStrings.xml" in z.namelist():
                tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in tree.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                    t = si.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                    shared_strings.append(t.text if t is not None else "")

            sheet_tree = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            sheet_data = sheet_tree.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData")
            if sheet_data is None:
                return []

            for row in sheet_data.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                r_vals = []
                for c in row.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                    t_attr = c.get("t")
                    v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                    val = v.text if v is not None else ""
                    if t_attr == "s" and val.isdigit() and int(val) < len(shared_strings):
                        val = shared_strings[int(val)]
                    r_vals.append(val)

                if len(r_vals) >= 3 and r_vals[0] and "/" in r_vals[0] and r_vals[0] != "FECHA TRANSACCIÓN":
                    rows.append((r_vals[0].strip(), r_vals[1].strip(), r_vals[2].strip()))
        return rows

    def _read_csv_rows(self, file_path: Path) -> list[tuple[str, str, str]]:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        rows = []
        reader = csv.reader(io.StringIO(text))
        for r in reader:
            if len(r) >= 3 and r[0] and "/" in r[0] and "FECHA" not in r[0].upper():
                rows.append((r[0].strip(), r[1].strip(), r[2].strip()))
        return rows

    def _parse_transaction_row(self, dt_str: str, raw_desc: str, amount_str: str, fallback_idx: int) -> NormalizedTransaction | None:
        # Parse date (DD/MM/YYYY)
        try:
            tx_date = datetime.strptime(dt_str, "%d/%m/%Y").date()
        except ValueError:
            return None

        # Parse amount
        clean_amt_str = amount_str.replace("$", "").replace(" ", "").replace(",", "")
        try:
            amt_dec = Decimal(clean_amt_str)
        except Exception:
            return None

        # Classify transaction type & clean description
        clean_desc, tx_type, source_acc, target_acc = self._classify_and_clean(raw_desc, amt_dec)
        abs_amount = abs(amt_dec)

        # Generate unique reference
        ref = f"TDC-{tx_date.strftime('%Y%m%d')}-{fallback_idx}-{int(abs_amount * 100)}"

        return NormalizedTransaction(
            reference=ref,
            date=tx_date,
            time="",
            amount=abs_amount,
            currency="USD",
            description=clean_desc,
            raw_description=raw_desc,
            tx_type=tx_type,
            source_account=source_acc,
            target_account=target_acc,
        )

    def _classify_and_clean(self, desc: str, amt: Decimal) -> tuple[str, TransactionType, str | None, str | None]:
        d_upper = desc.upper()

        # Card payment (Abono a cuenta)
        if "ABONO A SU CUENTA" in d_upper or ("ABONO" in d_upper and amt > 0):
            return "Pago TDC Banesco", TransactionType.TRANSFER, "BanPa Personal", "TDC - Banesco"

        # Refund / Credit Note
        if "NOTA DE CREDITO" in d_upper or "REEMBOLSO" in d_upper:
            cleaned = re.sub(r"^NOTA DE CREDITO\s*", "", desc, flags=re.IGNORECASE).strip()
            return f"Reembolso {cleaned}", TransactionType.REFUND, None, None

        # Expense / Purchase
        cleaned = self._clean_merchant_name(desc)
        return cleaned, TransactionType.EXPENSE, None, None

    def _clean_merchant_name(self, desc: str) -> str:
        # Strip common prefixes
        cleaned = re.sub(r"^(COMPRA \(RETAIL\)|COMPRA USA|COMPRA POS)\s*", "", desc, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"Regular Charge$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"Intereses de Compra.*$", "", cleaned, flags=re.IGNORECASE).strip()

        # Specific merchant cleanups
        if "NETFLIX" in cleaned.upper():
            return "Netflix"
        if "DISNEYPLUS" in cleaned.upper() or "DISNEY" in cleaned.upper():
            return "Disney+"
        if "SPOTIFY" in cleaned.upper():
            return "Spotify"
        if "ANTHROPIC" in cleaned.upper():
            return "Anthropic"
        if "DAILY EXPENSES" in cleaned.upper():
            return "Daily Expenses"
        if "GOOGLE ONE" in cleaned.upper():
            return "Google One"
        if "AMAZON" in cleaned.upper():
            return "Amazon"
        if "TIENDAS DAKA" in cleaned.upper() or "@TIENDASDAKA" in cleaned.upper():
            return "Tiendas Daka"
        if "REDVITAL" in cleaned.upper():
            return "Redvital"
        if "MEYBY" in cleaned.upper():
            return "Farmacia Meyby"
        if "FARMAIGNACIO" in cleaned.upper():
            return "Farmaignacio"
        if "MULTIMAX" in cleaned.upper():
            return "Multimax"
        if "SEGURO DE VIDA" in cleaned.upper():
            return "Seguro de Vida" if "ITBMS" not in cleaned.upper() else "Seguro de Vida (ITBMS)"
        if "ROBO Y FRAUDE" in cleaned.upper():
            return "Seguro Robo y Fraude" if "ITBMS" not in cleaned.upper() else "Seguro Robo y Fraude (ITBMS)"
        if "INTERESES" in cleaned.upper():
            return "Intereses TDC"
        if "MEMBRESIA" in cleaned.upper():
            return "Membresía Anual TDC" if "ITBMS" not in cleaned.upper() else "Membresía Anual TDC (ITBMS)"

        return re.sub(r"\s+", " ", cleaned).strip()
