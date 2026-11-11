"""Résultats attendus, calculés À LA MAIN à partir de generate.DATASET.

Ils ne sont volontairement PAS recalculés avec le code testé : sinon un bug dans le
traitement produirait aussi un résultat attendu faux et le test passerait.
"""

from decimal import Decimal as D

FR1 = "FR7610000000000000000000001"
FR3 = "FR7610000000000000000000003"
FR2 = "FR7620000000000000000000002"
DE1 = "DE89300000000000000001"
ES1 = "ES9100000000000000000001"
NL1 = "NL91INGB0000000001"
TN1 = "TN5910000000000000000001"

FILES = {
    "transactions_2026-01-01.csv": 5,
    "transactions_2026-01-02.csv": 6,
    "transactions_2026-01-03.csv": 7,
}
TOTAL_TRANSACTIONS = 18
TOTAL_AMOUNT = D("62276.49")

SENT_BY_IBAN = {
    FR1: D("9499.99"),   # T001 1200 + T004 300 + T011 1000 + T014 4999.99 + T018 2000
    FR3: D("900.00"),    # T007 800 + T013 100
    FR2: D("14999.99"),  # T002 5000 + T009 9999.99
    DE1: D("10950.50"),  # T003 7500.50 + T010 450 + T015 3000
    ES1: D("8700.00"),   # T005 2500 + T012 6200
    NL1: D("5075.26"),   # T006 5000.01 + T017 75.25
    TN1: D("12150.75"),  # T008 150.75 + T016 12000
}

SENT_BY_BANK = {
    "BNP Paribas": D("10399.99"),  # FR1 + FR3
    "Societe Generale": D("14999.99"),
    "Deutsche Bank": D("10950.50"),
    "Santander": D("8700.00"),
    "ING": D("5075.26"),
    "BIAT": D("12150.75"),
}

RECEIVED_BY_IBAN = {
    DE1: D("12275.24"),  # T001 1200 + T009 9999.99 + T011 1000 + T017 75.25
    ES1: D("19450.00"),  # T002 5000 + T010 450 + T016 12000 + T018 2000
    FR1: D("12600.51"),  # T003 7500.50 + T006 5000.01 + T013 100
    NL1: D("6500.00"),   # T004 300 + T012 6200
    FR2: D("7650.74"),   # T005 2500 + T008 150.75 + T014 4999.99
    TN1: D("3800.00"),   # T007 800 + T015 3000
}

# > 5000 strictement. T002 (5000.00) et T014 (4999.99) ne doivent PAS être flaggées.
FLAGGED_IDS = {"T003", "T006", "T009", "T012", "T016"}
