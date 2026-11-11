"""Q2 — Traitements. Toutes les fonctions de ce module sont PURES :

    - aucune lecture/écriture (fichier, base, réseau, logs) ;
    - aucune modification des arguments reçus ;
    - même entrée -> même sortie.

Les montants sont des Decimal pour éviter les erreurs d'arrondi des float.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

FLAG_THRESHOLD = Decimal("5000")


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    datetime_transaction: datetime
    iban_origine: str
    pays_source: str
    banque_source: str
    iban_destinataire: str
    pays_destinataire: str
    montant: Decimal


@dataclass(frozen=True)
class FlaggedTransaction:
    transaction: Transaction
    is_flagged: bool


@dataclass(frozen=True)
class ProcessingResult:
    transactions: tuple[FlaggedTransaction, ...]
    sent_by_iban: Mapping[str, Decimal]
    sent_by_bank: Mapping[str, Decimal]
    received_by_iban: Mapping[str, Decimal]


def _sum_by(
    transactions: Iterable[Transaction], key: Callable[[Transaction], str]
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for tx in transactions:
        k = key(tx)
        totals[k] = totals.get(k, Decimal("0")) + tx.montant
    return dict(sorted(totals.items()))


def sum_sent_by_iban(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    """Somme des montants envoyés par IBAN d'origine."""
    return _sum_by(transactions, lambda tx: tx.iban_origine)


def sum_sent_by_bank(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    """Somme des montants envoyés par banque source."""
    return _sum_by(transactions, lambda tx: tx.banque_source)


def sum_received_by_iban(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    """Somme des montants reçus par IBAN destinataire."""
    return _sum_by(transactions, lambda tx: tx.iban_destinataire)


def is_flagged(tx: Transaction, threshold: Decimal = FLAG_THRESHOLD) -> bool:
    """Une transaction est flaggée si son montant est STRICTEMENT au-dessus du seuil."""
    return tx.montant > threshold


def flag_transactions(
    transactions: Iterable[Transaction], threshold: Decimal = FLAG_THRESHOLD
) -> tuple[FlaggedTransaction, ...]:
    return tuple(FlaggedTransaction(tx, is_flagged(tx, threshold)) for tx in transactions)


def process(
    transactions: Iterable[Transaction], threshold: Decimal = FLAG_THRESHOLD
) -> ProcessingResult:
    """Applique l'ensemble des traitements à un lot de transactions."""
    txs = tuple(transactions)
    return ProcessingResult(
        transactions=flag_transactions(txs, threshold),
        sent_by_iban=sum_sent_by_iban(txs),
        sent_by_bank=sum_sent_by_bank(txs),
        received_by_iban=sum_received_by_iban(txs),
    )
