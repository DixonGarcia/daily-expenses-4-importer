"""Tests for Banesco Panama TDC parser."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from daily_expenses_importer.parsers.banesco_panama_tdc import BanescoPanamaTdcParser
from daily_expenses_importer.parsers.base import TransactionType


def test_banesco_panama_tdc_parses_csv(tmp_path: Path):
    csv_content = """FECHA TRANSACCIÓN,DESCRIPCIÓN,MONTO
24/08/2026,COMPRA (RETAIL)NETFLIX.COM,-10.98
14/08/2026,COMPRA (RETAIL)ANTHROPIC,-20.12
10/08/2026,ABONO A SU CUENTAFT26222DVVB0V,22.81
18/07/2026,NOTA DE CREDITOGOOGLE*GOOGLE ONE,2.31
17/07/2026,ITBMS SEGURO DE VIDARegular Charge,-0.14
"""
    file_path = tmp_path / "tdc_test.csv"
    file_path.write_text(csv_content, encoding="utf-8")

    parser = BanescoPanamaTdcParser()
    assert parser.supports(file_path, file_path.read_bytes())

    txs = parser.parse(file_path)
    assert len(txs) == 5

    # Chronologically sorted
    # 17/07/2026: Seguro de Vida (ITBMS)
    assert txs[0].date == date(2026, 7, 17)
    assert txs[0].amount == Decimal("0.14")
    assert txs[0].description == "Seguro de Vida (ITBMS)"
    assert txs[0].tx_type == TransactionType.EXPENSE

    # 18/07/2026: Refund
    assert txs[1].date == date(2026, 7, 18)
    assert txs[1].amount == Decimal("2.31")
    assert txs[1].tx_type == TransactionType.REFUND

    # 10/08/2026: Transfer (Card payment)
    assert txs[2].date == date(2026, 8, 10)
    assert txs[2].amount == Decimal("22.81")
    assert txs[2].tx_type == TransactionType.TRANSFER
    assert txs[2].source_account == "BanPa Personal"
    assert txs[2].target_account == "TDC - Banesco"

    # 14/08/2026: Anthropic
    assert txs[3].date == date(2026, 8, 14)
    assert txs[3].amount == Decimal("20.12")
    assert txs[3].description == "Anthropic"

    # 24/08/2026: Netflix
    assert txs[4].date == date(2026, 8, 24)
    assert txs[4].amount == Decimal("10.98")
    assert txs[4].description == "Netflix"
