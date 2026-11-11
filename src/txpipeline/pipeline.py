"""Orchestration d'une exécution : lister -> (déjà traité ?) -> récupérer -> parser ->
traiter -> insérer. Un fichier en erreur n'empêche pas le traitement des autres, mais
l'exécution est marquée en échec (code de sortie != 0) pour faire échouer la CI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import db, loader, processing, storage
from .config import Settings
from .retry import FaultInjector

log = logging.getLogger(__name__)


class Source(Protocol):
    def list_names(self) -> list[str]: ...
    def fetch(self, name: str) -> bytes: ...


@dataclass
class LocalSource:
    """Niveau 1 : CSV lus depuis un dossier local."""

    directory: Path

    def list_names(self) -> list[str]:
        return [p.name for p in loader.list_local_files(self.directory)]

    def fetch(self, name: str) -> bytes:
        return loader.read_local_file(self.directory / name)


@dataclass
class S3Source:
    """Niveau 2 : CSV récupérés depuis le S3 local, avec retry."""

    client: object
    bucket: str
    prefix: str
    attempts: int = 3
    base_delay: float = 0.5
    fail_download_times: int = 0

    def list_names(self) -> list[str]:
        return [k[len(self.prefix):] for k in storage.list_csv_keys(self.client, self.bucket,
                                                                     self.prefix)]

    def fetch(self, name: str) -> bytes:
        fault = FaultInjector(self.fail_download_times, f"S3 indisponible pour {name}")
        return storage.download_with_retry(
            self.client, self.bucket, self.prefix + name,
            attempts=self.attempts, base_delay=self.base_delay, fault=fault,
        )


@dataclass
class RunReport:
    processed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        return (f"{len(self.processed)} traité(s), {len(self.skipped)} ignoré(s) "
                f"(déjà traités), {len(self.failed)} en échec")


def process_one(name: str, source: Source, connect: db.Connect, settings: Settings,
                report: RunReport) -> None:
    with connect() as conn:
        if db.is_already_processed(conn, file_name=name):
            report.skipped.append(name)
            return
    content = source.fetch(name)
    digest = loader.file_hash(content)
    with connect() as conn:
        if db.is_already_processed(conn, file_hash=digest):
            log.info("%s : contenu identique à un fichier déjà traité -> ignoré", name)
            report.skipped.append(name)
            return

    transactions = loader.parse_transactions(content, source=name)  # chargement
    result = processing.process(transactions)                         # traitement pur
    inserted = db.insert_with_retry(
        connect, name, digest, result,
        attempts=settings.retry_attempts, base_delay=settings.retry_base_delay,
        fault=FaultInjector(settings.fail_insert_times, f"base indisponible pour {name}"),
    )
    if inserted:
        flagged = sum(ft.is_flagged for ft in result.transactions)
        log.info("%s : %d transactions insérées (%d flaggées)", name, len(transactions), flagged)
        report.processed.append(name)
    else:
        report.skipped.append(name)


def run(source: Source, connect: db.Connect, settings: Settings) -> RunReport:
    report = RunReport()
    for name in source.list_names():
        try:
            process_one(name, source, connect, settings, report)
        except Exception as exc:  # un fichier en erreur ne bloque pas les autres
            log.error("%s : ÉCHEC -> %s: %s", name, type(exc).__name__, exc)
            report.failed[name] = f"{type(exc).__name__}: {exc}"
    log.info("Bilan : %s", report.summary())
    return report


def build_source(kind: str, settings: Settings, input_dir: str | None = None) -> Source:
    if kind == "local":
        return LocalSource(Path(input_dir or settings.data_dir))
    if kind == "s3":
        return S3Source(
            client=storage.make_client(settings),
            bucket=settings.s3_bucket,
            prefix=settings.s3_prefix,
            attempts=settings.retry_attempts,
            base_delay=settings.retry_base_delay,
            fail_download_times=settings.fail_download_times,
        )
    raise ValueError(f"source inconnue : {kind}")
