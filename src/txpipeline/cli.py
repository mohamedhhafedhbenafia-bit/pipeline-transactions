"""Point d'entrée en ligne de commande : python -m txpipeline <commande>

    generate   génère les CSV déterministes dans DATA_DIR
    upload     envoie les CSV locaux dans le S3 (bucket/prefix)
    init-db    crée le schéma PostgreSQL
    reset-db   supprime et recrée le schéma (démos)
    run        traite les fichiers (--source local|s3)
    pipeline   enchaîne generate -> upload -> init-db -> run (s3)
    schedule   relance `run` toutes les N secondes (worker de production)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import db, generate, loader, storage
from .config import Settings
from .pipeline import build_source, run
from .scheduler import serve

log = logging.getLogger("txpipeline")


def cmd_generate(settings: Settings, args) -> int:
    for path in generate.generate(args.out or settings.data_dir):
        log.info("généré : %s", path)
    return 0


def cmd_upload(settings: Settings, args) -> int:
    client = storage.make_client(settings)
    storage.ensure_bucket(client, settings.s3_bucket)
    files = loader.list_local_files(args.src or settings.data_dir)
    if not files:
        log.error("aucun CSV à envoyer dans %s", args.src or settings.data_dir)
        return 1
    for path in files:
        key = settings.s3_prefix + path.name
        storage.upload_bytes(client, settings.s3_bucket, key, path.read_bytes())
        log.info("envoyé : s3://%s/%s", settings.s3_bucket, key)
    return 0


def cmd_init_db(settings: Settings, args) -> int:
    with db.make_connect(settings.database_url)() as conn:
        db.init_schema(conn)
    log.info("schéma initialisé")
    return 0


def cmd_reset_db(settings: Settings, args) -> int:
    with db.make_connect(settings.database_url)() as conn:
        db.reset_schema(conn)
        db.init_schema(conn)
    log.warning("base réinitialisée (toutes les données supprimées)")
    return 0


def cmd_run(settings: Settings, args) -> int:
    source = build_source(args.source, settings, getattr(args, "input", None))
    report = run(source, db.make_connect(settings.database_url), settings)
    return 0 if report.ok else 1


def cmd_pipeline(settings: Settings, args) -> int:
    args.out = args.src = None
    args.source = "s3"
    for step in (cmd_generate, cmd_upload, cmd_init_db, cmd_run):
        code = step(settings, args)
        if code:
            return code
    return 0


def cmd_schedule(settings: Settings, args) -> int:
    serve(settings, args.source, args.interval, args.max_runs)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="txpipeline", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="génère les CSV")
    g.add_argument("--out", type=Path)
    g.set_defaults(func=cmd_generate)

    u = sub.add_parser("upload", help="envoie les CSV dans le S3")
    u.add_argument("--src", type=Path)
    u.set_defaults(func=cmd_upload)

    sub.add_parser("init-db", help="crée le schéma").set_defaults(func=cmd_init_db)
    sub.add_parser("reset-db", help="vide la base (démo)").set_defaults(func=cmd_reset_db)

    r = sub.add_parser("run", help="traite les fichiers")
    r.add_argument("--source", choices=["local", "s3"], default="s3")
    r.add_argument("--input", type=Path, help="dossier (source local)")
    r.set_defaults(func=cmd_run)

    sub.add_parser("pipeline", help="generate+upload+init-db+run").set_defaults(func=cmd_pipeline)

    s = sub.add_parser("schedule", help="exécution périodique")
    s.add_argument("--source", choices=["local", "s3"], default="s3")
    s.add_argument("--interval", type=float, default=60)
    s.add_argument("--max-runs", type=int)
    s.set_defaults(func=cmd_schedule)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    args = build_parser().parse_args(argv)
    try:
        return args.func(Settings.from_env(), args)
    except Exception as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
