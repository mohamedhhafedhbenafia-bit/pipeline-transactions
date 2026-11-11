"""Q1 — Génération déterministe des fichiers CSV de transactions.

Les données sont FIXES (pas d'aléatoire) : les résultats attendus sont calculés à la
main dans tests/expected.py, ce qui rend la pipeline testable de bout en bout.

Colonnes demandées par le sujet + deux colonnes ajoutées car indispensables :
    - transaction_id : identifiant unique (clé primaire en base)
    - montant        : nécessaire pour les sommes et le flag > 5000
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

COLUMNS = (
    "transaction_id",
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
)

# Comptes de référence : (iban, pays, banque)
FR1 = ("FR7610000000000000000000001", "FR", "BNP Paribas")
FR3 = ("FR7610000000000000000000003", "FR", "BNP Paribas")  # 2e compte BNP
FR2 = ("FR7620000000000000000000002", "FR", "Societe Generale")
DE1 = ("DE89300000000000000001", "DE", "Deutsche Bank")
ES1 = ("ES9100000000000000000001", "ES", "Santander")
NL1 = ("NL91INGB0000000001", "NL", "ING")
TN1 = ("TN5910000000000000000001", "TN", "BIAT")


def _tx(tx_id: str, when: str, src: tuple, dst: tuple, amount: str) -> dict[str, str]:
    return {
        "transaction_id": tx_id,
        "datetime_transaction": when,
        "iban_origine": src[0],
        "pays_source": src[1],
        "banque_source": src[2],
        "iban_destinataire": dst[0],
        "pays_destinataire": dst[1],
        "montant": amount,
    }


# 3 fichiers de 5, 6 et 7 transactions (contrainte du sujet : 5 à 10 par fichier).
DATASET: dict[str, list[dict[str, str]]] = {
    "transactions_2026-01-01.csv": [
        _tx("T001", "2026-01-01T09:00:00", FR1, DE1, "1200.00"),
        _tx("T002", "2026-01-01T10:30:00", FR2, ES1, "5000.00"),  # limite : NON flaggée
        _tx("T003", "2026-01-01T11:15:00", DE1, FR1, "7500.50"),  # flaggée
        _tx("T004", "2026-01-01T14:00:00", FR1, NL1, "300.00"),
        _tx("T005", "2026-01-01T16:45:00", ES1, FR2, "2500.00"),
    ],
    "transactions_2026-01-02.csv": [
        _tx("T006", "2026-01-02T08:00:00", NL1, FR1, "5000.01"),  # flaggée (juste au-dessus)
        _tx("T007", "2026-01-02T09:20:00", FR3, TN1, "800.00"),
        _tx("T008", "2026-01-02T12:00:00", TN1, FR2, "150.75"),
        _tx("T009", "2026-01-02T13:30:00", FR2, DE1, "9999.99"),  # flaggée
        _tx("T010", "2026-01-02T15:10:00", DE1, ES1, "450.00"),
        _tx("T011", "2026-01-02T18:00:00", FR1, DE1, "1000.00"),
    ],
    "transactions_2026-01-03.csv": [
        _tx("T012", "2026-01-03T07:45:00", ES1, NL1, "6200.00"),  # flaggée
        _tx("T013", "2026-01-03T09:00:00", FR3, FR1, "100.00"),
        _tx("T014", "2026-01-03T10:10:00", FR1, FR2, "4999.99"),
        _tx("T015", "2026-01-03T11:30:00", DE1, TN1, "3000.00"),
        _tx("T016", "2026-01-03T13:00:00", TN1, ES1, "12000.00"),  # flaggée
        _tx("T017", "2026-01-03T15:30:00", NL1, DE1, "75.25"),
        _tx("T018", "2026-01-03T17:00:00", FR1, ES1, "2000.00"),
    ],
}


def render_csv(rows: list[dict[str, str]]) -> str:
    """Fonction pure : transforme une liste de lignes en texte CSV."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def generate(out_dir: str | Path) -> list[Path]:
    """Écrit les CSV du DATASET dans out_dir et retourne les chemins créés."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, rows in DATASET.items():
        path = out / name
        path.write_text(render_csv(rows), encoding="utf-8", newline="")
        paths.append(path)
    return paths
