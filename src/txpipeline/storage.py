"""Niveau 2 — Stockage des CSV dans un S3 local (MinIO, compatible API S3).

Le code n'utilise que l'API S3 standard via boto3 : il fonctionne à l'identique avec
Garage, SeaweedFS, RustFS ou AWS S3 en changeant simplement S3_ENDPOINT_URL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import Settings
from .retry import FaultInjector, SimulatedFailure, call_with_retry

log = logging.getLogger(__name__)

RETRYABLE = (BotoCoreError, ClientError, SimulatedFailure)


def make_client(settings: Settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        # boto3 a ses propres retries : on les désactive pour que NOTRE mécanisme
        # soit celui qui s'applique (et soit visible dans les logs).
        config=Config(
            retries={"max_attempts": 1, "mode": "standard"},
            connect_timeout=3,
            read_timeout=10,
            s3={"addressing_style": "path"},
        ),
    )


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
        log.info("bucket %s créé", bucket)


def upload_bytes(client, bucket: str, key: str, data: bytes) -> None:
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType="text/csv")


def list_csv_keys(client, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".csv")]
    return sorted(keys)


def download(client, bucket: str, key: str, fault: FaultInjector | None = None) -> bytes:
    if fault is not None:
        fault.maybe_fail()
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def download_with_retry(
    client,
    bucket: str,
    key: str,
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    fault: FaultInjector | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bytes:
    """Niveau 2 Q4 — Récupération d'un fichier avec retry."""
    kwargs = {"sleep": sleep} if sleep else {}
    return call_with_retry(
        lambda: download(client, bucket, key, fault),
        attempts=attempts,
        base_delay=base_delay,
        retry_on=RETRYABLE,
        description=f"téléchargement s3://{bucket}/{key}",
        **kwargs,
    )
