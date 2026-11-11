# Pipeline data de transactions financières — intégration continue

Pipeline complète **CSV → S3 local → traitement Python → PostgreSQL → dashboard**,
sécurisée par une CI GitHub Actions (tests unitaires, tests d'intégration, scénarios
d'échec, retry, anti-doublon) et déployée par une CD Docker.

| Niveau | Contenu | Statut |
|---|---|---|
| 1 | Génération CSV, traitement pur, schéma SQL, insertion, CI, tests, retry, anti-doublon | ✅ |
| 2 | Stockage des CSV dans un S3 local (SeaweedFS), lecture depuis le S3, retry de téléchargement | ✅ |
| 3 | CD Docker : image publiée, stack de prod (S3 + DB + worker planifié + dashboard), smoke test, déploiement VM | ✅ |

---

## Architecture

```mermaid
flowchart LR
    G[generate.py<br/>CSV déterministes] -->|upload| S3[(S3 local<br/>SeaweedFS<br/>incoming/)]
    S3 -->|download + retry| L[loader.py<br/>parsing + validation]
    L --> P[processing.py<br/>fonctions pures]
    P -->|insert + retry<br/>1 transaction SQL| DB[(PostgreSQL)]
    DB --> D[Dashboard<br/>Streamlit]
    W[worker planifié<br/>scheduler.py] -.toutes les N s.-> L
```

## Structure du projet

```
pipeline-transactions/
├── src/txpipeline/
│   ├── generate.py      # Q1  génération déterministe des CSV
│   ├── loader.py        # Q2  chargement + validation (I/O)
│   ├── processing.py    # Q2  traitements PURS (sommes, flag > 5000)
│   ├── schema.sql       # Q3  schéma relationnel
│   ├── db.py            # Q3/Q7 insertion idempotente + retry
│   ├── storage.py       # N2  client S3 + retry de téléchargement
│   ├── retry.py         #     retry générique (backoff) + injection de pannes
│   ├── pipeline.py      # Q4  orchestration (source locale ou S3)
│   ├── scheduler.py     # N3  exécution périodique (worker)
│   ├── config.py        #     configuration par variables d'environnement
│   └── cli.py           #     python -m txpipeline <commande>
├── tests/
│   ├── expected.py      # résultats attendus calculés À LA MAIN
│   ├── unit/            # tests unitaires (sans service)
│   ├── integration/     # Q5/Q7/N2 sur vrai PostgreSQL + S3 (schéma/bucket isolés)
│   └── e2e/             # Q5 vérifie la base réelle après exécution de la CLI
├── dashboard/app.py     # dashboard Streamlit connecté à la base
├── scripts/inject_bug.py# Q6 injection de bugs pour les scénarios d'échec
├── deploy/              # entrypoint SeaweedFS
├── docs/                # scénarios d'échec, déploiement, captures
├── .github/workflows/   # ci.yml (CI) et cd.yml (CD)
├── docker-compose.yml   # postgres + s3 (+ worker + dashboard en profil prod)
└── Dockerfile
```

## Démarrage rapide

Prérequis : Python ≥ 3.10, Docker Desktop.

```bash
# 1. Environnement Python
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/macOS : source .venv/bin/activate)
pip install -e ".[dev,dashboard]"

# 2. Services : PostgreSQL (port 5433) + S3 SeaweedFS (port 8333)
docker compose up -d --wait postgres s3

# 3. Pipeline complète : generate -> upload S3 -> init-db -> run
python -m txpipeline pipeline

# 4. Rejeu : rien n'est retraité
python -m txpipeline run --source s3
#   ... Bilan : 0 traité(s), 3 ignoré(s) (déjà traités), 0 en échec

# 5. Tests
pytest tests/unit                                   # sans service
set TXP_REQUIRE_SERVICES=1 && pytest tests/integration   # (bash : TXP_REQUIRE_SERVICES=1 pytest ...)
set TXP_E2E=1 && pytest tests/e2e
```

> **Windows :**
> - si les accents s'affichent mal : `set PYTHONIOENCODING=utf-8` ;
> - si le projet est dans un dossier au chemin long (ex. Bureau\M2 …), `pip install`
>   échoue (limite de 260 caractères). Créer alors le venv dans un chemin court :
>   `python -m venv C:\Users\<vous>\.venvs\txpipeline` puis
>   `C:\Users\<vous>\.venvs\txpipeline\Scripts\activate`.

### Commandes de la CLI

| Commande | Rôle |
|---|---|
| `generate [--out DIR]` | écrit les CSV dans `data/raw` |
| `upload [--src DIR]` | envoie les CSV dans `s3://transactions/incoming/` |
| `init-db` | crée le schéma (idempotent) |
| `reset-db` | vide la base (démos) |
| `run --source s3\|local [--input DIR]` | traite les fichiers (code retour 1 si un fichier échoue) |
| `pipeline` | enchaîne generate → upload → init-db → run |
| `schedule --interval 30` | relance `run` en boucle (worker de prod) |

### Stack de production complète (niveau 3)

```bash
docker compose --profile prod up -d --build --wait
python -m txpipeline generate && python -m txpipeline upload
# -> le worker traite les fichiers en < 30 s
# Dashboard : http://localhost:8501
```

---

## Réponses aux questions

### Niveau 1

**Q1 — Génération** (`generate.py`). 3 fichiers de 5, 6 et 7 transactions **fixes**.
Deux colonnes sont ajoutées car indispensables : `transaction_id` (clé primaire) et
`montant` (absent de l'énoncé mais nécessaire aux sommes et au flag). Les données
contiennent volontairement des cas limites : 5000.00 (non flaggée), 5000.01 et
4999.99, deux comptes dans la même banque (BNP) pour distinguer « par IBAN » de
« par banque ».

**Q2 — Chargement / traitement séparés.**
`loader.py` lit et valide (colonnes, dates, montants > 0 à 2 décimales, IBAN, pays,
5 à 10 lignes, ids uniques). `processing.py` ne contient que des **fonctions pures**
(pas d'I/O, entrées non modifiées — vérifié par `test_functions_are_pure`) :
`sum_sent_by_iban`, `sum_sent_by_bank`, `sum_received_by_iban`, `is_flagged`
(montant **strictement** > 5000), `process`. Les montants sont des `Decimal`.

**Q3 — Base relationnelle** (`schema.sql`).

```mermaid
erDiagram
    processed_files ||--o{ transactions : contient
    processed_files ||--o{ agg_sent_by_iban : produit
    processed_files ||--o{ agg_sent_by_bank : produit
    processed_files ||--o{ agg_received_by_iban : produit
    processed_files { int id PK; text file_name UK; char64 file_hash UK; int row_count; timestamptz processed_at }
    transactions { text transaction_id PK; int file_id FK; timestamp datetime_transaction; text iban_origine; char2 pays_source; text banque_source; text iban_destinataire; char2 pays_destinataire; numeric montant; bool is_flagged }
    agg_sent_by_iban { int file_id PK; text iban PK; numeric total }
    agg_sent_by_bank { int file_id PK; text bank PK; numeric total }
    agg_received_by_iban { int file_id PK; text iban PK; numeric total }
```

Les agrégats sont stockés **par fichier** puis consolidés par des vues
(`v_sent_by_iban`, `v_sent_by_bank`, `v_received_by_iban`, `v_flagged_transactions`) :
chaque nouveau fichier ajoute des lignes sans réécrire les anciennes.

**Q4 — Pipeline** (`.github/workflows/ci.yml`) : lint + tests unitaires, puis
démarrage PostgreSQL + S3 → génération → dépôt S3 → schéma → traitement → rejeu
anti-doublon → vérification de la base → tests d'intégration.

**Q5 — Test d'intégration** : `tests/db_assertions.py` compare la base aux valeurs
calculées à la main dans `tests/expected.py` (nombre de fichiers et de lignes,
total, sommes par IBAN/banque, reçus, transactions flaggées). Utilisé par
`tests/integration` (schéma isolé) et `tests/e2e` (base réelle après la CLI).

**Q6 — Scénarios d'échec** : voir [docs/scenarios-echec.md](docs/scenarios-echec.md).
Lancer le workflow CI manuellement avec `inject_bug = generation | processing |
aggregation` et faire les captures.

**Q7 — Panne d'insertion + retry** : `FAIL_INSERT_TIMES=N` fait échouer N fois
l'insertion **de chaque fichier**, *après* l'insertion partielle des transactions.
`db.insert_with_retry` réessaie 3 fois avec backoff exponentiel (0.5 s, 1 s), avec une
nouvelle connexion à chaque tentative.

```
$ FAIL_INSERT_TIMES=2 python -m txpipeline run
WARNING insertion transactions_2026-01-01.csv : tentative 1/3 échouée (base indisponible ...) -> nouvel essai dans 0.5s
WARNING insertion transactions_2026-01-01.csv : tentative 2/3 échouée (base indisponible ...) -> nouvel essai dans 1.0s
INFO    insertion transactions_2026-01-01.csv : réussi à la tentative 3/3
```

### Anti-doublon : un fichier n'est jamais traité deux fois

1. Avant de télécharger : le **nom** est-il dans `processed_files` ? → ignoré.
2. Après téléchargement : le **hash SHA-256** du contenu existe-t-il ? → ignoré
   (même fichier renommé).
3. L'entrée `processed_files` et toutes les données du fichier sont écrites dans
   **une seule transaction SQL** : en cas de panne, le rollback efface tout, le
   fichier n'est pas marqué traité et le retry repart de zéro. En cas de succès, le
   fichier est marqué traité atomiquement.
4. `INSERT ... ON CONFLICT DO NOTHING` + contraintes `UNIQUE` : même deux workers
   en parallèle ne peuvent pas insérer deux fois.

Tests : `test_replay_never_processes_a_file_twice`,
`test_same_content_under_another_name_is_skipped`,
`test_insert_retry_recovers_without_duplicates`,
`test_insert_failure_leaves_no_partial_data_then_recovers`.

### Niveau 2 — S3 local

- **S3 choisi : SeaweedFS** (`chrislusf/seaweedfs:4.50`), cité par l'énoncé et
  auto-hébergé. Le code n'utilise que l'API S3 standard (boto3) : passer à Garage ou
  RustFS ne demande que de changer `S3_ENDPOINT_URL`.
- Le S3 est démarré en début de pipeline (`docker compose up -d --wait postgres s3`)
  et les CSV y sont déposés (`upload`, préfixe `incoming/`).
- Le traitement lit depuis le S3 (`S3Source`), plus depuis le disque.
- **Retry de téléchargement** : `storage.download_with_retry` (3 tentatives, backoff).
  Les retries internes de boto3 sont désactivés pour que notre mécanisme soit
  celui qui s'applique. Simulation : `FAIL_DOWNLOAD_TIMES=N`.

### Niveau 3 — CD Docker

`.github/workflows/cd.yml`, déclenché après une CI verte sur `main` :
1. build de l'image et publication sur `ghcr.io` ;
2. déploiement de la stack de prod sur le runner (S3 + PostgreSQL + **worker** qui
   relance la pipeline toutes les `SCHEDULE_INTERVAL` secondes + dashboard), dépôt
   de fichiers dans le S3 et vérification que le worker les a traités seul ;
3. déploiement sur une VM via SSH si les secrets `DEPLOY_*` sont définis
   (voir [docs/deploiement.md](docs/deploiement.md)).

## Configuration

Toutes les valeurs ont un défaut utilisable en local ; voir `.env.example`.

| Variable | Défaut | Rôle |
|---|---|---|
| `DATABASE_URL` | `postgresql://pipeline:pipeline@localhost:5433/transactions` | base cible |
| `S3_ENDPOINT_URL` | `http://localhost:8333` | S3 local |
| `S3_BUCKET` / `S3_PREFIX` | `transactions` / `incoming/` | emplacement des CSV |
| `RETRY_ATTEMPTS` / `RETRY_BASE_DELAY` | `3` / `0.5` | retry |
| `FAIL_INSERT_TIMES` / `FAIL_DOWNLOAD_TIMES` | `0` | pannes simulées par fichier |
