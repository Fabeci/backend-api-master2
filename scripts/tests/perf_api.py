#!/usr/bin/env python3
"""Test de charge des API de lecture SOMAPRO (local, reproductible).

Mesure : latence moyenne, p50/p95/p99, débit, taux d'erreur.
Cible : serveur de développement Django (SQLite) — PAS une mesure de production.

Usage :
  python3 scripts/tests/perf_api.py --duration 20 --concurrency 5
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

ENDPOINTS = [
    "/api/v1/cours/",
    "/api/v1/progress/blocs/",
    "/api/v1/annees-scolaires/",
    "/api/v1/notifications/",
]


def login(base: str, email: str, password: str) -> str:
    reponse = requests.post(
        f"{base}/api/v1/login/",
        json={"email": email, "password": password},
        timeout=30,
    )
    reponse.raise_for_status()
    return reponse.json()["data"]["token"]


def worker(base: str, token: str, duree: float, latences: list, erreurs: list, stop: threading.Event):
    session = requests.Session()
    session.headers.update({"Authorization": f"Token {token}"})
    index = 0
    while not stop.is_set():
        chemin = ENDPOINTS[index % len(ENDPOINTS)]
        index += 1
        debut = time.perf_counter()
        try:
            reponse = session.get(f"{base}{chemin}", timeout=30)
            duree_ms = (time.perf_counter() - debut) * 1000
            if reponse.status_code >= 400:
                erreurs.append({"endpoint": chemin, "status": reponse.status_code})
            else:
                latences.append(duree_ms)
        except Exception as exc:  # noqa: BLE001
            erreurs.append({"endpoint": chemin, "error": str(exc)[:120]})


def percentile(valeurs: list[float], p: float) -> float:
    if not valeurs:
        return 0.0
    triees = sorted(valeurs)
    index = min(len(triees) - 1, max(0, int(round((p / 100) * (len(triees) - 1)))))
    return round(triees[index], 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--email", default="chat.test@example.com")
    parser.add_argument("--password", default="Test@1234")
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    token = login(args.base, args.email, args.password)
    latences: list[float] = []
    erreurs: list = []
    stop = threading.Event()

    debut = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(worker, args.base, token, args.duration, latences, erreurs, stop)
            for _ in range(args.concurrency)
        ]
        time.sleep(args.duration)
        stop.set()
        for future in futures:
            future.result()
    ecoule = time.perf_counter() - debut

    total = len(latences) + len(erreurs)
    resultat = {
        "date": datetime.now(timezone.utc).isoformat(),
        "environnement": {
            "base": args.base,
            "serveur": "Django runserver (dev)",
            "base_de_donnees": "SQLite",
            "concurrence": args.concurrency,
            "duree_s": round(ecoule, 2),
        },
        "requetes": {
            "total": total,
            "succes": len(latences),
            "erreurs": len(erreurs),
            "taux_erreur_pct": round(100 * len(erreurs) / total, 2) if total else 0.0,
            "debit_req_s": round(total / ecoule, 2) if ecoule else 0.0,
        },
        "latence_ms": {
            "moyenne": round(statistics.mean(latences), 2) if latences else 0.0,
            "min": round(min(latences), 2) if latences else 0.0,
            "p50": percentile(latences, 50),
            "p95": percentile(latences, 95),
            "p99": percentile(latences, 99),
            "max": round(max(latences), 2) if latences else 0.0,
        },
        "endpoints": ENDPOINTS,
        "erreurs_echantillon": erreurs[:10],
    }

    sortie = Path("doc/tests/raw/perf.json")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(resultat, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
