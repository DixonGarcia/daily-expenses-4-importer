"""Generic CSV parser with auto-header detection for dates, amounts, descriptions, categories, and accounts."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from daily_expenses_importer.parsers.base import BaseParser, NormalizedTransaction, TransactionType

_DATE_HEADERS = {"date", "fecha", "fecha y hora", "fecha/hora", "datetime", "date & time", "date and time", "transaction date", "fecha transaccion", "fecha transacción", "f. operacion", "f. valor"}
_DESC_HEADERS = {"description", "descripción", "descripcion", "concepto", "detalle", "merchant", "payee", "comercio", "notas", "nota"}
_AMOUNT_HEADERS = {"amount", "monto", "importe", "valor"}
_DEBIT_HEADERS = {"debit", "debito", "débito", "gasto", "egreso", "cargos", "expense", "expenses"}
_CREDIT_HEADERS = {"credit", "credito", "crédito", "ingreso", "abono", "abonos", "income", "incomes"}
_REF_HEADERS = {"reference", "referencia", "ref", "id", "secuencia", "número", "numero", "nro operacion"}
_CAT_HEADERS = {"category", "categoría", "categoria", "rubro", "clasificación", "clasificacion"}
_TYPE_HEADERS = {"type", "tipo", "tipo movimiento", "tipo de movimiento", "tipo_movimiento"}
_ACCOUNT_HEADERS = {"account", "cuenta", "target account", "target_account", "cuenta destino", "cuenta_destino"}
_SOURCE_ACC_HEADERS = {"source account", "source_account", "cuenta origen", "cuenta_origen", "desde cuenta"}
_TIME_HEADERS = {"time", "hora", "horario"}


class GenericCsvParser(BaseParser):
    """Parses standard CSV / TSV bank statements and custom template files."""

    @property
    def name(self) -> str:
        return "generic_csv"

    def supports(self, file_path: Path, sample_bytes: bytes) -> bool:
        if file_path.suffix.lower() not in {".csv", ".txt", ".tsv"}:
            return False
        try:
            sample_text = sample_bytes.decode("utf-8", errors="ignore")[:4096]
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample_text)
            return dialect.delimiter in {",", ";", "\t"}
        except Exception:
            sample_text = sample_bytes.decode("utf-8", errors="ignore")[:2048]
            return any(d in sample_text for d in (",", ";", "\t"))

    def parse(self, file_path: Path) -> list[NormalizedTransaction]:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            return []

        # Sniff delimiter
        sample = text[:4096]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            if "\t" in sample:
                delimiter = "\t"
            elif ";" in sample:
                delimiter = ";"

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            return []

        # Map field names
        field_map = self._map_fields(reader.fieldnames)
        if "date" not in field_map or ("amount" not in field_map and "debit" not in field_map):
            return []

        transactions = []
        for idx, row in enumerate(reader, 1):
            tx = self._parse_row(row, field_map, fallback_index=idx)
            if tx is not None:
                transactions.append(tx)

        return transactions

    def _map_fields(self, fieldnames: list[str]) -> dict[str, str]:
        mapped = {}
        for f in fieldnames:
            clean = f.strip().lower().replace("_", " ")
            if clean in _DATE_HEADERS and "date" not in mapped:
                mapped["date"] = f
            elif clean in _DESC_HEADERS and "desc" not in mapped:
                mapped["desc"] = f
            elif clean in _AMOUNT_HEADERS and "amount" not in mapped:
                mapped["amount"] = f
            elif clean in _DEBIT_HEADERS and "debit" not in mapped:
                mapped["debit"] = f
            elif clean in _CREDIT_HEADERS and "credit" not in mapped:
                mapped["credit"] = f
            elif clean in _REF_HEADERS and "ref" not in mapped:
                mapped["ref"] = f
            elif clean in _CAT_HEADERS and "category" not in mapped:
                mapped["category"] = f
            elif clean in _TYPE_HEADERS and "type" not in mapped:
                mapped["type"] = f
            elif clean in _ACCOUNT_HEADERS and "account" not in mapped:
                mapped["account"] = f
            elif clean in _SOURCE_ACC_HEADERS and "source_account" not in mapped:
                mapped["source_account"] = f
            elif clean in _TIME_HEADERS and "time" not in mapped:
                mapped["time"] = f
        return mapped

    def _parse_row(self, row: dict[str, str], field_map: dict[str, str], fallback_index: int) -> NormalizedTransaction | None:
        raw_date = row.get(field_map.get("date", ""), "").strip()
        parsed_date, extracted_time = self._parse_datetime(raw_date)
        if not parsed_date:
            return None

        raw_desc = row.get(field_map.get("desc", ""), "").strip()
        ref = row.get(field_map.get("ref", ""), "").strip()
        if not ref:
            ref = f"CSV-{parsed_date.strftime('%Y%m%d')}-{fallback_index}"

        # Resolve amount & tx_type
        amount = Decimal("0")
        tx_type = TransactionType.EXPENSE

        if "debit" in field_map or "credit" in field_map:
            debit_val = self._parse_amount(row.get(field_map.get("debit", ""), ""))
            credit_val = self._parse_amount(row.get(field_map.get("credit", ""), ""))
            if debit_val > Decimal("0"):
                amount = debit_val
                tx_type = TransactionType.EXPENSE
            elif credit_val > Decimal("0"):
                amount = credit_val
                tx_type = TransactionType.INCOME
            else:
                return None
        elif "amount" in field_map:
            val_str = row.get(field_map["amount"], "").strip()
            amount_val = self._parse_amount(val_str)
            if amount_val < Decimal("0") or "-" in val_str:
                amount = abs(amount_val)
                tx_type = TransactionType.EXPENSE
            elif amount_val > Decimal("0"):
                amount = amount_val
                tx_type = TransactionType.INCOME
            else:
                return None
        else:
            return None

        # Check explicit type column if present
        raw_type = row.get(field_map.get("type", ""), "").strip().lower()
        if raw_type:
            if "transfer" in raw_type or "transf" in raw_type:
                tx_type = TransactionType.TRANSFER
            elif "inc" in raw_type or "ingr" in raw_type or "abono" in raw_type:
                tx_type = TransactionType.INCOME
            elif "exp" in raw_type or "gast" in raw_type or "egr" in raw_type:
                tx_type = TransactionType.EXPENSE

        # Category and Account
        category = row.get(field_map.get("category", ""), "").strip() or None
        account_raw = row.get(field_map.get("account", ""), "").strip()
        source_acc = row.get(field_map.get("source_account", ""), "").strip() or None
        target_acc = account_raw or None
        time_str = row.get(field_map.get("time", ""), "").strip() or extracted_time

        # Handle transfer accounts format: "Source -> Target"
        if account_raw and "->" in account_raw:
            tx_type = TransactionType.TRANSFER
            parts = [p.strip() for p in account_raw.split("->", 1)]
            source_acc = parts[0]
            target_acc = parts[1]

        clean_desc = self._clean_description(raw_desc)
        return NormalizedTransaction(
            reference=ref,
            date=parsed_date,
            time=time_str,
            amount=amount,
            currency="USD",
            description=clean_desc,
            raw_description=raw_desc,
            tx_type=tx_type,
            category=category,
            source_account=source_acc,
            target_account=target_acc,
        )

    def _parse_datetime(self, text: str) -> tuple[date | None, str]:
        if not text:
            return None, ""
        clean_text = text.strip()
        time_str = ""

        formats = [
            ("%Y-%m-%d %H:%M:%S", True),
            ("%Y-%m-%d %H:%M", True),
            ("%d/%m/%Y %H:%M:%S", True),
            ("%d/%m/%Y %H:%M", True),
            ("%Y/%m/%d %H:%M:%S", True),
            ("%Y/%m/%d %H:%M", True),
            ("%d-%m-%Y %H:%M:%S", True),
            ("%d-%m-%Y %H:%M", True),
            ("%Y-%m-%d", False),
            ("%d/%m/%Y", False),
            ("%m/%d/%Y", False),
            ("%d-%m-%Y", False),
            ("%Y/%m/%d", False),
            ("%d.%m.%Y", False),
            ("%Y%m%d", False),
        ]
        for fmt, has_time in formats:
            try:
                dt = datetime.strptime(clean_text, fmt)
                if has_time:
                    time_str = dt.strftime("%H:%M:%S")
                return dt.date(), time_str
            except ValueError:
                continue

        # Fallback: split by space or T
        parts = re.split(r"[ T]", clean_text)
        if len(parts) >= 2:
            time_str = parts[1]
            date_part = parts[0]
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]:
                try:
                    d = datetime.strptime(date_part, fmt).date()
                    return d, time_str
                except ValueError:
                    continue

        return None, ""

    def _parse_amount(self, text: str) -> Decimal:
        if not text:
            return Decimal("0")
        clean = text.replace("$", "").replace("€", "").replace("USD", "").replace(" ", "").strip()
        is_negative = False
        if clean.startswith("(") and clean.endswith(")"):
            clean = clean[1:-1].strip()
            is_negative = True
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        try:
            val = Decimal(clean)
            return -val if is_negative else val
        except Exception:
            return Decimal("0")

    def _clean_description(self, desc: str) -> str:
        cleaned = re.sub(r"^(COMPRA \(RETAIL\)|COMPRA USA|COMPRA POS:?)\s*", "", desc, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned if cleaned else desc
