"""Q5 + Q7 + niveau 2 — Tests d'intégration sur un vrai PostgreSQL et un vrai S3 local."""

from __future__ import annotations

import dataclasses

import pytest

from tests import expected
from tests.db_assertions import assert_database_state
from txpipeline import storage
from txpipeline.generate import generate
from txpipeline.pipeline import LocalSource, build_source, run

pytestmark = pytest.mark.integration


@pytest.fixture
def csv_dir(tmp_path):
    generate(tmp_path)
    return tmp_path


@pytest.fixture
def uploaded(s3, settings, csv_dir):
    for path in sorted(csv_dir.glob("*.csv")):
        storage.upload_bytes(s3, settings.s3_bucket, settings.s3_prefix + path.name,
                             path.read_bytes())
    return settings


def count_rows(connect, table="transactions") -> int:
    with connect() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- Niveau 1 : source locale ----------------------------------------------------------

def test_local_pipeline_inserts_expected_values(connect, settings, csv_dir):
    report = run(LocalSource(csv_dir), connect, settings)
    assert report.ok and len(report.processed) == 3
    with connect() as conn:
        assert_database_state(conn)


# --- Niveau 2 : source S3 ---------------------------------------------------------------

def test_s3_pipeline_inserts_expected_values(connect, uploaded):
    report = run(build_source("s3", uploaded), connect, uploaded)
    assert report.ok
    assert sorted(report.processed) == sorted(expected.FILES)
    with connect() as conn:
        assert_database_state(conn)


# --- Anti-doublon ------------------------------------------------------------------------

def test_replay_never_processes_a_file_twice(connect, uploaded):
    source = build_source("s3", uploaded)
    run(source, connect, uploaded)
    second = run(source, connect, uploaded)
    assert second.processed == [] and len(second.skipped) == 3
    with connect() as conn:
        assert_database_state(conn)


def test_same_content_under_another_name_is_skipped(connect, uploaded, s3, csv_dir):
    run(build_source("s3", uploaded), connect, uploaded)
    copy = (csv_dir / "transactions_2026-01-01.csv").read_bytes()
    storage.upload_bytes(s3, uploaded.s3_bucket, uploaded.s3_prefix + "zz_copie.csv", copy)
    report = run(build_source("s3", uploaded), connect, uploaded)
    assert report.processed == [] and "zz_copie.csv" in report.skipped
    assert count_rows(connect) == expected.TOTAL_TRANSACTIONS


# --- Q7 : panne d'insertion + retry -------------------------------------------------------

def test_insert_retry_recovers_without_duplicates(connect, uploaded):
    flaky = dataclasses.replace(uploaded, fail_insert_times=2, retry_attempts=3)
    report = run(build_source("s3", flaky), connect, flaky)
    assert report.ok and len(report.processed) == 3
    with connect() as conn:
        assert_database_state(conn)  # aucune ligne en double malgré 6 échecs partiels


def test_insert_failure_leaves_no_partial_data_then_recovers(connect, uploaded):
    broken = dataclasses.replace(uploaded, fail_insert_times=5, retry_attempts=3)
    report = run(build_source("s3", broken), connect, broken)
    assert not report.ok and len(report.failed) == 3
    assert count_rows(connect) == 0                     # rollback complet
    assert count_rows(connect, "processed_files") == 0  # fichiers non marqués traités

    report = run(build_source("s3", uploaded), connect, uploaded)  # panne résolue
    assert report.ok and len(report.processed) == 3
    with connect() as conn:
        assert_database_state(conn)


# --- Niveau 2 Q4 : panne de téléchargement + retry --------------------------------------

def test_download_retry_recovers(connect, uploaded):
    flaky = dataclasses.replace(uploaded, fail_download_times=2, retry_attempts=3)
    report = run(build_source("s3", flaky), connect, flaky)
    assert report.ok
    with connect() as conn:
        assert_database_state(conn)


def test_download_failure_marks_run_failed(connect, uploaded):
    broken = dataclasses.replace(uploaded, fail_download_times=3, retry_attempts=3)
    report = run(build_source("s3", broken), connect, broken)
    assert len(report.failed) == 3
    assert all("RetryError" in err for err in report.failed.values())
    assert count_rows(connect, "processed_files") == 0


def test_invalid_file_fails_run_but_others_are_processed(connect, uploaded, s3):
    storage.upload_bytes(s3, uploaded.s3_bucket, uploaded.s3_prefix + "zz_bad.csv",
                         b"transaction_id,montant\nT999,abc\n")
    report = run(build_source("s3", uploaded), connect, uploaded)
    assert list(report.failed) == ["zz_bad.csv"]
    assert len(report.processed) == 3
