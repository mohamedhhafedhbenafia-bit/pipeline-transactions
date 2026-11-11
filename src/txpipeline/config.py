"""Configuration lue depuis les variables d'environnement (12-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_prefix: str
    data_dir: str
    retry_attempts: int
    retry_base_delay: float
    # Injection de pannes (Q7 / niveau 2 Q4) : nombre d'échecs simulés PAR FICHIER.
    fail_insert_times: int
    fail_download_times: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL", "postgresql://pipeline:pipeline@localhost:5433/transactions"
            ),
            s3_endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://localhost:8333"),
            s3_access_key=os.environ.get("S3_ACCESS_KEY", "pipeline"),
            s3_secret_key=os.environ.get("S3_SECRET_KEY", "pipeline-secret"),
            s3_bucket=os.environ.get("S3_BUCKET", "transactions"),
            s3_prefix=os.environ.get("S3_PREFIX", "incoming/"),
            data_dir=os.environ.get("DATA_DIR", "data/raw"),
            retry_attempts=_int("RETRY_ATTEMPTS", 3),
            retry_base_delay=_float("RETRY_BASE_DELAY", 0.5),
            fail_insert_times=_int("FAIL_INSERT_TIMES", 0),
            fail_download_times=_int("FAIL_DOWNLOAD_TIMES", 0),
        )
