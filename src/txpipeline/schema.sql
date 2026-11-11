-- Q3 — Schéma relationnel des résultats de traitement.
-- Idempotent : peut être rejoué sans erreur (CREATE ... IF NOT EXISTS / OR REPLACE).
--
--  processed_files 1 ── n transactions
--                  1 ── n agg_sent_by_iban
--                  1 ── n agg_sent_by_bank
--                  1 ── n agg_received_by_iban
--
-- Les agrégats sont stockés PAR FICHIER puis consolidés par des vues : un nouveau
-- fichier ajoute des lignes sans jamais réécrire les précédentes, et tout ce qui
-- concerne un fichier est inséré dans la même transaction SQL que son entrée dans
-- processed_files (registre anti-doublon).

CREATE TABLE IF NOT EXISTS processed_files (
    id            SERIAL PRIMARY KEY,
    file_name     TEXT        NOT NULL UNIQUE,
    file_hash     CHAR(64)    NOT NULL UNIQUE,   -- SHA-256 du contenu
    row_count     INTEGER     NOT NULL CHECK (row_count >= 0),
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id        TEXT          PRIMARY KEY,
    file_id               INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    datetime_transaction  TIMESTAMP     NOT NULL,
    iban_origine          TEXT          NOT NULL,
    pays_source           CHAR(2)       NOT NULL,
    banque_source         TEXT          NOT NULL,
    iban_destinataire     TEXT          NOT NULL,
    pays_destinataire     CHAR(2)       NOT NULL,
    montant               NUMERIC(14,2) NOT NULL CHECK (montant > 0),
    is_flagged            BOOLEAN       NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_flagged ON transactions(is_flagged) WHERE is_flagged;

CREATE TABLE IF NOT EXISTS agg_sent_by_iban (
    file_id  INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    iban     TEXT          NOT NULL,
    total    NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (file_id, iban)
);

CREATE TABLE IF NOT EXISTS agg_sent_by_bank (
    file_id  INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    bank     TEXT          NOT NULL,
    total    NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (file_id, bank)
);

CREATE TABLE IF NOT EXISTS agg_received_by_iban (
    file_id  INTEGER       NOT NULL REFERENCES processed_files(id) ON DELETE CASCADE,
    iban     TEXT          NOT NULL,
    total    NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (file_id, iban)
);

-- Vues consolidées (tous fichiers confondus) : utilisées par les tests et le dashboard.
CREATE OR REPLACE VIEW v_sent_by_iban AS
    SELECT iban, SUM(total)::NUMERIC(14,2) AS total_sent
    FROM agg_sent_by_iban GROUP BY iban;

CREATE OR REPLACE VIEW v_sent_by_bank AS
    SELECT bank, SUM(total)::NUMERIC(14,2) AS total_sent
    FROM agg_sent_by_bank GROUP BY bank;

CREATE OR REPLACE VIEW v_received_by_iban AS
    SELECT iban, SUM(total)::NUMERIC(14,2) AS total_received
    FROM agg_received_by_iban GROUP BY iban;

CREATE OR REPLACE VIEW v_flagged_transactions AS
    SELECT t.*, f.file_name
    FROM transactions t JOIN processed_files f ON f.id = t.file_id
    WHERE t.is_flagged;
