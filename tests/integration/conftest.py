"""Fixtures d'intégration : chaque test reçoit un schéma PostgreSQL et un bucket S3
neufs et isolés, supprimés à la fin. Les tests sont donc indépendants et rejouables.

Si les services ne sont pas joignables, les tests sont ignorés en local, mais
ÉCHOUENT si TXP_REQUIRE_SERVICES=1 (c'est le cas en CI).
"""

from __future__ import annotations

import dataclasses
import os
import uuid

import psycopg
import pytest

from txpipeline import db, storage
from txpipeline.config import Settings


def _unavailable(reason: str):
    if os.environ.get("TXP_REQUIRE_SERVICES") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
def settings() -> Settings:
    base = Settings.from_env()
    return dataclasses.replace(
        base,
        s3_bucket=f"test-{uuid.uuid4().hex[:12]}",
        retry_base_delay=0.01,
        fail_insert_times=0,
        fail_download_times=0,
    )


@pytest.fixture
def connect(settings):
    schema = f"test_{uuid.uuid4().hex[:12]}"
    try:
        admin = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as exc:
        _unavailable(f"PostgreSQL indisponible : {exc}")
    admin.execute(f"CREATE SCHEMA {schema}")
    connect_fn = db.make_connect(settings.database_url, options=f"-c search_path={schema}")
    with connect_fn() as conn:
        db.init_schema(conn)
    yield connect_fn
    admin.execute(f"DROP SCHEMA {schema} CASCADE")
    admin.close()


@pytest.fixture
def s3(settings):
    client = storage.make_client(settings)
    try:
        storage.ensure_bucket(client, settings.s3_bucket)
    except Exception as exc:
        _unavailable(f"S3 indisponible : {exc}")
    yield client
    for key in storage.list_csv_keys(client, settings.s3_bucket, ""):
        client.delete_object(Bucket=settings.s3_bucket, Key=key)
    client.delete_bucket(Bucket=settings.s3_bucket)
