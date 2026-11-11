from decimal import Decimal

import pytest

from tests import expected
from txpipeline.generate import COLUMNS, DATASET, generate, render_csv
from txpipeline.loader import InvalidCsvError, file_hash, parse_transactions


def test_generation_is_deterministic(tmp_path):
    first = {p.name: p.read_bytes() for p in generate(tmp_path / "a")}
    second = {p.name: p.read_bytes() for p in generate(tmp_path / "b")}
    assert first == second
    assert {n: file_hash(c) for n, c in first.items()} == {
        n: file_hash(c) for n, c in second.items()
    }


def test_generated_files_match_spec(tmp_path):
    paths = generate(tmp_path)
    assert {p.name: len(parse_transactions(p.read_bytes(), p.name)) for p in paths} == \
        expected.FILES
    for p in paths:
        header = p.read_text(encoding="utf-8").splitlines()[0]
        assert tuple(header.split(",")) == COLUMNS


def test_transaction_ids_unique_across_files():
    ids = [row["transaction_id"] for rows in DATASET.values() for row in rows]
    assert len(ids) == len(set(ids)) == expected.TOTAL_TRANSACTIONS


def test_parse_types():
    tx = parse_transactions(render_csv(DATASET["transactions_2026-01-01.csv"]))[2]
    assert tx.transaction_id == "T003"
    assert tx.montant == Decimal("7500.50")
    assert tx.datetime_transaction.hour == 11


def _rows(**override):
    rows = [dict(r) for r in DATASET["transactions_2026-01-01.csv"]]
    rows[0].update(override)
    return rows


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"montant": "-10"}, "montant doit être > 0"),
        ({"montant": "12,50"}, "montant invalide"),
        ({"montant": "1.234"}, "plus de 2 décimales"),
        ({"datetime_transaction": "31/01/2026"}, "date invalide"),
        ({"pays_source": "France"}, "code pays invalide"),
        ({"iban_origine": "XX"}, "IBAN invalide"),
        ({"banque_source": ""}, "vide"),
        ({"transaction_id": "T002"}, "dupliqué"),
    ],
)
def test_invalid_rows_are_rejected(override, message):
    with pytest.raises(InvalidCsvError, match=message):
        parse_transactions(render_csv(_rows(**override)))


def test_missing_column_is_rejected():
    text = render_csv(DATASET["transactions_2026-01-01.csv"])
    text = text.replace("montant", "amount", 1)
    with pytest.raises(InvalidCsvError, match="colonnes manquantes"):
        parse_transactions(text)


def test_row_count_bounds():
    rows = DATASET["transactions_2026-01-01.csv"][:4]
    with pytest.raises(InvalidCsvError, match="entre 5 et 10"):
        parse_transactions(render_csv(rows))
