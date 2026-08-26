"""Generic CSV parser with auto-header detection for dates, amounts, and descriptions."""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from daily_expenses_importer.parsers.base import BaseParser, NormalizedTransaction, TransactionType

_DATE_HEADERS = {"date", "fecha", "transaction date", "fecha transaccion", "fecha transacción", "f. operacion", "f. valor"}
_DESC_HEADERS = {"description", "descripción", "descripcion", "concepto", "detalle", "merchant", "payee", "comercio"}
_AMOUNT_HEADERS = {"amount", "monto", "importe", "valor"}
_DEBIT_HEADERS = {"debit", "debito", "débito", "gasto", "egreso", "cargos"}
_CREDIT_HEADERS = {"credit", "credito", "crédito", "ingreso", "abono", "abonos"}
_REF_HEADERS = {"reference", "referencia", "ref", "id", "secuencia", "número", "numero", "nro operacion"}


class GenericCsvParser(BaseParser):
    """Parses standard CSV bank and credit card statements."""

    @property
    def name(self) -> str:
        return "generic_csv"

    def supports(self, file_path: Path, sample_bytes: bytes) -> bool:
        if file_path.suffix.lower() not in {".csv", ".txt"}:
            return False
        try:
            sample_text = sample_bytes.decode("utf-8", errors="ignore")[:4096]
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample_text)
            return dialect.delimiter in {",", ";", "\t"}
        except Exception:
            return False

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
        return mapped

    def _parse_row(self, row: dict[str, str], field_map: dict[str, str], fallback_index: int) -> NormalizedTransaction | None:
        raw_date = row.get(field_map.get("date", ""), "").strip()
        parsed_date = self._parse_date(raw_date)
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

        clean_desc = self._clean_description(raw_desc)
        return NormalizedTransaction(
            reference=ref,
            date=parsed_date,
            time="",
            amount=amount,
            currency="USD",
            description=clean_desc,
            raw_description=raw_desc,
            tx_type=tx_type,
        )

    def _parse_date(self, text: str) -> date | None:
        if not text:
            return None
        formats = [
            "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d",
            "%d.%m.%Y", "%Y%m%d"
        ]
        # Remove time component if present
        date_part = text.split(" ")[0].split("T")[0].strip()
        for fmt in formats:
            try:
                return datetime.strptime(date_part, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_amount(self, text: str) -> Decimal:
        if not text:
            return Decimal("0")
        clean = text.replace("$", "").replace("€", "").replace(" ", "").strip()
        # Handle comma as decimal or thousand separator
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        try:
            return Decimal(clean)
        except Exception:
            return Decimal("0")

    def _clean_description(self, desc: str) -> str:
        # Strip common noise
        cleaned = re.sub(r"^(COMPRA \(RETAIL\)|COMPRA USA|COMPRA POS|PAGO)\s*", "", desc, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or desc
