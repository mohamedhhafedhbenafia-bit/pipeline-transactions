"""Vérifications de l'état de la base, partagées par les tests d'intégration et e2e."""

from tests import expected


def fetch_dict(conn, sql: str) -> dict:
    return dict(conn.execute(sql).fetchall())


def assert_database_state(conn) -> None:
    files = fetch_dict(conn, "SELECT file_name, row_count FROM processed_files")
    assert files == expected.FILES

    count, total = conn.execute("SELECT COUNT(*), SUM(montant) FROM transactions").fetchone()
    assert count == expected.TOTAL_TRANSACTIONS
    assert total == expected.TOTAL_AMOUNT

    assert fetch_dict(conn, "SELECT iban, total_sent FROM v_sent_by_iban") == \
        expected.SENT_BY_IBAN
    assert fetch_dict(conn, "SELECT bank, total_sent FROM v_sent_by_bank") == \
        expected.SENT_BY_BANK
    assert fetch_dict(conn, "SELECT iban, total_received FROM v_received_by_iban") == \
        expected.RECEIVED_BY_IBAN

    flagged = {r[0] for r in conn.execute("SELECT transaction_id FROM v_flagged_transactions")}
    assert flagged == expected.FLAGGED_IDS
