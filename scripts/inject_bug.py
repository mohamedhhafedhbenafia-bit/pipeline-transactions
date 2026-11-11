"""Q6 — Introduit volontairement un bug pour montrer que la pipeline CI échoue.

    python scripts/inject_bug.py generation   # CSV générés invalides (montant "7500,50")
    python scripts/inject_bug.py processing   # flag >= 5000 au lieu de > 5000
    python scripts/inject_bug.py aggregation  # "reçu par IBAN" calculé sur l'IBAN d'origine
    python scripts/inject_bug.py --list

Le script modifie les sources en place (à utiliser sur une branche dédiée ou en CI
via le workflow « CI » lancé manuellement avec l'option inject_bug). Annuler avec :
    git checkout -- src/
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "txpipeline"

BUGS = {
    "generation": (
        "generate.py",
        '_tx("T003", "2026-01-01T11:15:00", DE1, FR1, "7500.50")',
        '_tx("T003", "2026-01-01T11:15:00", DE1, FR1, "7500,50")',
        "Le générateur écrit un montant avec une virgule décimale -> CSV invalide",
    ),
    "processing": (
        "processing.py",
        "return tx.montant > threshold",
        "return tx.montant >= threshold",
        "Le flag utilise >= : la transaction de 5000.00 pile est flaggée à tort",
    ),
    "aggregation": (
        "processing.py",
        "return _sum_by(transactions, lambda tx: tx.iban_destinataire)",
        "return _sum_by(transactions, lambda tx: tx.iban_origine)",
        "La somme des montants reçus est calculée sur l'IBAN d'origine",
    ),
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "--list"}:
        for name, (_, _, _, desc) in BUGS.items():
            print(f"{name:12} {desc}")
        return 0
    name = argv[0]
    if name == "none":
        return 0
    if name not in BUGS:
        print(f"bug inconnu : {name} (choix : {', '.join(BUGS)})", file=sys.stderr)
        return 2
    file, old, new, desc = BUGS[name]
    path = ROOT / file
    source = path.read_text(encoding="utf-8")
    if old not in source:
        print(f"motif introuvable dans {path} (déjà injecté ?)", file=sys.stderr)
        return 1
    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    print(f"BUG INJECTÉ [{name}] dans {file} : {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
