"""Mécanisme de retry générique avec backoff exponentiel + injection de pannes.

Utilisé pour :
    - l'insertion en base (niveau 1, Q7)
    - le téléchargement depuis le S3 (niveau 2, Q4)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)


class RetryError(RuntimeError):
    """Toutes les tentatives ont échoué."""


class SimulatedFailure(ConnectionError):
    """Panne simulée (réseau / base indisponible)."""


def call_with_retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    factor: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    description: str = "opération",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Appelle func() jusqu'à `attempts` fois. Attente : base_delay * factor**(n-1)."""
    if attempts < 1:
        raise ValueError("attempts doit être >= 1")
    for attempt in range(1, attempts + 1):
        try:
            result = func()
        except retry_on as exc:
            if attempt == attempts:
                log.error("%s : échec définitif après %d tentatives (%s)",
                          description, attempt, exc)
                raise RetryError(f"{description} : échec après {attempts} tentatives") from exc
            delay = base_delay * factor ** (attempt - 1)
            log.warning(
                "%s : tentative %d/%d échouée (%s) -> nouvel essai dans %.1fs",
                description, attempt, attempts, exc, delay,
            )
            sleep(delay)
        else:
            if attempt > 1:
                log.info("%s : réussi à la tentative %d/%d", description, attempt, attempts)
            return result
    raise AssertionError("inatteignable")


class FaultInjector:
    """Fait échouer les `times` premiers appels à maybe_fail() (pour simuler une panne)."""

    def __init__(self, times: int = 0, label: str = "panne simulée") -> None:
        self.remaining = max(0, times)
        self.label = label
        self.calls = 0

    def maybe_fail(self) -> None:
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise SimulatedFailure(f"{self.label} (appel n°{self.calls})")
