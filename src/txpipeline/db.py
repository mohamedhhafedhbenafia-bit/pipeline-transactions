"""Q3 / Q7 — Base de données : création du schéma et insertion idempotente.

Garantie anti-doublon :
    1. le fichier est enregistré dans processed_files (UNIQUE sur le nom ET le hash) ;
    2. ses transactions et agrégats sont insérés ;
    3. tout est COMMIT dans UNE SEULE transaction SQL.
Si l'insertion plante à l'étape 2, le ROLLBACK annule aussi l'étape 1 : un retry repart
d'une base propre. Si le fichier est déjà présent, ON CONFLICT DO NOTHING ne renvoie
aucune ligne et on n'insère rien (même en cas de deux workers concurrents).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib import resources

import psycopg

from .processing import ProcessingResult
from .retry import FaultInjector, SimulatedFailure, call_with_retry

log = logging.getLogger(__name__)

Connect = Callable[[], psycopg.Connection]


def make_connect(database_url: str, **kwargs) -> Connect:
    return lambda: psycopg.connect(database_url, connect_timeout=5, **kwargs)


def schema_sql() -> str:
    return resources.files("txpipeline").joinpath("schema.sql").read_text(encoding="utf-8")


def init_schema(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute(schema_sql())


def reset_schema(conn: psycopg.Connection) -> None:
    """Supprime toutes les tables (démos / tests manuels uniquement)."""
    with conn.transaction():
        conn.execute(
            "DROP TABLE IF EXISTS agg_received_by_iban, agg_sent_by_bank, agg_sent_by_iban,"
            " transactions, processed_files CASCADE"
        )


def is_already_processed(conn: psycopg.Connection, *, file_name: str | None = None,
                         file_hash: str | None = None) -> bool:
    row = conn.execute(
        "SELECT 1 FROM processed_files WHERE file_name = %s OR file_hash = %s",
        (file_name, file_hash),
    ).fetchone()
    return row is not None


def insert_file_results(
    conn: psycopg.Connection,
    file_name: str,
    file_hash: str,
    result: ProcessingResult,
    fault: FaultInjector | None = None,
) -> bool:
    """Insère les résultats d'un fichier. Retourne False si le fichier était déjà traité."""
    with conn.transaction():
        row = conn.execute(
            """INSERT INTO processed_files (file_name, file_hash, row_count)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING id""",
            (file_name, file_hash, len(result.transactions)),
        ).fetchone()
        if row is None:
            log.info("%s déjà traité -> ignoré", file_name)
            return False
        file_id = row[0]

        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO transactions (transaction_id, file_id, datetime_transaction,
                       iban_origine, pays_source, banque_source, iban_destinataire,
                       pays_destinataire, montant, is_flagged)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (t.transaction_id, file_id, t.datetime_transaction, t.iban_origine,
                     t.pays_source, t.banque_source, t.iban_destinataire,
                     t.pays_destinataire, t.montant, ft.is_flagged)
                    for ft in result.transactions
                    for t in (ft.transaction,)
                ],
            )
            # Panne simulée APRÈS une partie des insertions : prouve que le rollback
            # empêche toute donnée partielle / dupliquée.
            if fault is not None:
                fault.maybe_fail()
            for table, col, data in (
                ("agg_sent_by_iban", "iban", result.sent_by_iban),
                ("agg_sent_by_bank", "bank", result.sent_by_bank),
                ("agg_received_by_iban", "iban", result.received_by_iban),
            ):
                cur.executemany(
                    f"INSERT INTO {table} (file_id, {col}, total) VALUES (%s, %s, %s)",
                    [(file_id, k, v) for k, v in data.items()],
                )
    return True


def insert_with_retry(
    connect: Connect,
    file_name: str,
    file_hash: str,
    result: ProcessingResult,
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    fault: FaultInjector | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bool:
    """Q7 — Insertion avec retry. Chaque tentative ouvre une NOUVELLE connexion."""

    def attempt() -> bool:
        with connect() as conn:
            return insert_file_results(conn, file_name, file_hash, result, fault)

    kwargs = {"sleep": sleep} if sleep else {}
    return call_with_retry(
        attempt,
        attempts=attempts,
        base_delay=base_delay,
        retry_on=(psycopg.OperationalError, SimulatedFailure),
        description=f"insertion {file_name}",
        **kwargs,
    )
