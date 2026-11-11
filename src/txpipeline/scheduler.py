"""Niveau 3 — Exécution périodique : le worker de production relance la pipeline toutes
les N secondes pour traiter les nouveaux fichiers déposés dans le S3. Grâce au registre
processed_files, les fichiers déjà traités sont simplement ignorés.
"""

from __future__ import annotations

import logging
import signal
import threading

from . import db
from .config import Settings
from .pipeline import build_source, run

log = logging.getLogger(__name__)


def serve(settings: Settings, source_kind: str, interval: float,
          max_runs: int | None = None) -> None:
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: stop.set())
        except ValueError:  # pas dans le thread principal
            pass

    connect = db.make_connect(settings.database_url)
    runs = 0
    log.info("Scheduler démarré : source=%s, intervalle=%ss", source_kind, interval)
    while not stop.is_set():
        try:
            with connect() as conn:
                db.init_schema(conn)
            run(build_source(source_kind, settings), connect, settings)
        except Exception:
            log.exception("Exécution en échec, nouvel essai au prochain cycle")
        runs += 1
        if max_runs is not None and runs >= max_runs:
            break
        stop.wait(interval)
    log.info("Scheduler arrêté")
