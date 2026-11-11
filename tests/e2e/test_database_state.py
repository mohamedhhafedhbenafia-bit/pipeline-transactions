"""Q5 — Vérifie la base RÉELLE après une exécution de la pipeline par la CLI
(étapes `generate -> upload -> init-db -> run` de la CI ou du worker de production).

Activé seulement si TXP_E2E=1, car il lit la base par défaut (pas un schéma isolé).
"""

import os

import psycopg
import pytest

from tests.db_assertions import assert_database_state
from txpipeline.config import Settings

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("TXP_E2E") != "1", reason="TXP_E2E=1 requis"),
]


def test_database_contains_expected_values():
    with psycopg.connect(Settings.from_env().database_url) as conn:
        assert_database_state(conn)
