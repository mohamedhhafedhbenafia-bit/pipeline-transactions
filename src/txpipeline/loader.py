"""Q2 — Chargement des données (séparé des traitements).

Ce module lit des octets (disque local ; le S3 est dans storage.py) et les convertit
en objets Transaction en validant strictement le format. Un fichier invalide lève
InvalidCsvError : c'est ce qui fait échouer la pipeline si la génération est buggée.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .generate import COLUMNS
from .processing import Transaction

MIN_ROWS, MAX_ROWS = 5, 10
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_IBAN_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$")


class InvalidCsvError(ValueError):
    """Le contenu d'un fichier CSV ne respecte pas le format attendu."""


def file_hash(content: bytes) -> str:
    """Empreinte SHA-256 du contenu : sert d'identifiant anti-doublon."""
    return hashlib.sha256(content).hexdigest()


def _parse_row(row: dict[str, str], line: int, source: str) -> Transaction:
    def fail(msg: str) -> InvalidCsvError:
        return InvalidCsvError(f"{source}, ligne {line} : {msg}")

    for col in COLUMNS:
        if not (row.get(col) or "").strip():
            raise fail(f"colonne '{col}' vide")
    try:
        when = datetime.fromisoformat(row["datetime_transaction"])
    except ValueError as exc:
        raise fail(f"date invalide {row['datetime_transaction']!r}") from exc
    try:
        amount = Decimal(row["montant"])
    except InvalidOperation as exc:
        raise fail(f"montant invalide {row['montant']!r}") from exc
    if not amount.is_finite() or amount <= 0:
        raise fail(f"montant doit être > 0, reçu {row['montant']!r}")
    if amount.as_tuple().exponent < -2:
        raise fail(f"montant avec plus de 2 décimales {row['montant']!r}")
    for col in ("pays_source", "pays_destinataire"):
        if not _COUNTRY_RE.match(row[col]):
            raise fail(f"code pays invalide {row[col]!r} ({col})")
    for col in ("iban_origine", "iban_destinataire"):
        if not _IBAN_RE.match(row[col]):
            raise fail(f"IBAN invalide {row[col]!r} ({col})")

    return Transaction(
        transaction_id=row["transaction_id"].strip(),
        datetime_transaction=when,
        iban_origine=row["iban_origine"],
        pays_source=row["pays_source"],
        banque_source=row["banque_source"].strip(),
        iban_destinataire=row["iban_destinataire"],
        pays_destinataire=row["pays_destinataire"],
        montant=amount,
    )


def parse_transactions(content: bytes | str, source: str = "<memoire>") -> list[Transaction]:
    """Parse et valide le contenu d'un CSV de transactions."""
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text))
    header = tuple(reader.fieldnames or ())
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise InvalidCsvError(f"{source} : colonnes manquantes {missing}")

    transactions = [_parse_row(row, i, source) for i, row in enumerate(reader, start=2)]

    if not MIN_ROWS <= len(transactions) <= MAX_ROWS:
        raise InvalidCsvError(
            f"{source} : {len(transactions)} transactions, attendu entre {MIN_ROWS} et {MAX_ROWS}"
        )
    ids = [tx.transaction_id for tx in transactions]
    if len(ids) != len(set(ids)):
        raise InvalidCsvError(f"{source} : transaction_id dupliqué dans le fichier")
    return transactions


def list_local_files(directory: str | Path) -> list[Path]:
    """Liste triée des CSV d'un dossier local (niveau 1)."""
    return sorted(Path(directory).glob("*.csv"))


def read_local_file(path: str | Path) -> bytes:
    return Path(path).read_bytes()
