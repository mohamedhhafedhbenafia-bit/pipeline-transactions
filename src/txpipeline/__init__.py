"""txpipeline : pipeline data de transactions financières.

Modules :
    generate    -> génération déterministe des CSV (niveau 1, Q1)
    loader      -> chargement / parsing des CSV (I/O, niveau 1, Q2)
    processing  -> traitements purs (niveau 1, Q2)
    db          -> schéma + insertion idempotente avec retry (niveau 1, Q3/Q7)
    storage     -> S3 local avec retry de téléchargement (niveau 2)
    pipeline    -> orchestration d'une exécution
    scheduler   -> exécution périodique (niveau 3, CD)
"""

__version__ = "1.0.0"
