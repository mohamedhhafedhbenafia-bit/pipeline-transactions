import copy
from datetime import datetime
from decimal import Decimal

import pytest

from tests import expected
from txpipeline.generate import DATASET, render_csv
from txpipeline.loader import parse_transactions
from txpipeline.processing import (
    Transaction,
    is_flagged,
    process,
    sum_received_by_iban,
    sum_sent_by_bank,
    sum_sent_by_iban,
)


@pytest.fixture
def all_transactions() -> list[Transaction]:
    txs = []
    for name, rows in DATASET.items():
        txs += parse_transactions(render_csv(rows), source=name)
    return txs


def make_tx(amount: str, src="FR761", dst="DE891", bank="B") -> Transaction:
    return Transaction("X", datetime(2026, 1, 1), src, "FR", bank, dst, "DE", Decimal(amount))


def test_sum_sent_by_iban(all_transactions):
    assert sum_sent_by_iban(all_transactions) == expected.SENT_BY_IBAN


def test_sum_sent_by_bank(all_transactions):
    assert sum_sent_by_bank(all_transactions) == expected.SENT_BY_BANK


def test_sum_received_by_iban(all_transactions):
    assert sum_received_by_iban(all_transactions) == expected.RECEIVED_BY_IBAN


def test_totals_are_consistent(all_transactions):
    total = sum(t.montant for t in all_transactions)
    assert total == expected.TOTAL_AMOUNT
    assert sum(sum_sent_by_iban(all_transactions).values()) == total
    assert sum(sum_received_by_iban(all_transactions).values()) == total


@pytest.mark.parametrize(
    ("amount", "flagged"),
    [("4999.99", False), ("5000.00", False), ("5000.01", True), ("12000", True)],
)
def test_flag_threshold_is_strict(amount, flagged):
    assert is_flagged(make_tx(amount)) is flagged


def test_process_flags_expected_transactions(all_transactions):
    result = process(all_transactions)
    flagged = {ft.transaction.transaction_id for ft in result.transactions if ft.is_flagged}
    assert flagged == expected.FLAGGED_IDS
    assert len(result.transactions) == expected.TOTAL_TRANSACTIONS


def test_functions_are_pure(all_transactions):
    snapshot = copy.deepcopy(all_transactions)
    first = process(all_transactions)
    second = process(all_transactions)
    assert first == second                 # même entrée -> même sortie
    assert all_transactions == snapshot    # entrée non modifiée


def test_empty_input():
    result = process([])
    assert result.transactions == ()
    assert result.sent_by_iban == {} and result.sent_by_bank == {}
