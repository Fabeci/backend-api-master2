#!/usr/bin/env python3
"""Génère les figures SVG du chapitre « Validation » du mémoire."""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)


def svg(w, h, body, bg="#ffffff"):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="DejaVu Sans, Arial, sans-serif">'
        f'<rect width="{w}" height="{h}" fill="{bg}"/>{body}</svg>'
    )


# ── Figure 1 : couverture par module critique ──────────────────────────────
def couverture():
    data = [
        ("LMD (lmd.py)", 98), ("Progression (progression.py)", 94),
        ("Tableau de bord (views_stats.py)", 93), ("Difficulté (difficulte.py)", 92),
        ("Explication d'erreur", 88), ("Modèles analytics", 85),
        ("Chat (vues)", 85), ("RBAC (rbac.py)", 81),
        ("Moteur parcours", 80), ("Chat (service)", 78),
        ("Quiz tuteur", 75), ("Modèles évaluations", 72),
        ("RAG documentaire", 70), ("Publication", 69),
        ("Contrôle d'accès", 61), ("Permissions DRF", 32),
    ]
    W, H = 980, 930
    left, top, gap = 300, 70, 24
    bar_h, max_w = 22, 560
    body = [f'<text x="{W/2}" y="38" text-anchor="middle" font-size="20" font-weight="bold">'
            f'Couverture des modules critiques (exécution réelle)</text>']
    for i, (label, value) in enumerate(data):
        y = top + i * (bar_h + gap)
        w = int(max_w * value / 100)
        color = "#16a34a" if value >= 80 else ("#f59e0b" if value >= 60 else "#dc2626")
        body.append(f'<text x="{left-12}" y="{y+16}" text-anchor="end" font-size="12">{label}</text>')
        body.append(f'<rect x="{left}" y="{y}" width="{max_w}" height="{bar_h}" rx="6" fill="#eef2f7"/>')
        body.append(f'<rect x="{left}" y="{y}" width="{w}" height="{bar_h}" rx="6" fill="{color}"/>')
        body.append(f'<text x="{left+w+8}" y="{y+16}" font-size="12" font-weight="bold">{value} %</text>')
    body.append(f'<text x="{W/2}" y="{H-18}" text-anchor="middle" font-size="11" fill="#6b7280">'
                f'Couverture applicative globale : 40 % — les migrations, tests et fichiers vides sont exclus.</text>')
    return svg(W, H, "".join(body))


# ── Figure 2 : pyramide des tests ──────────────────────────────────────────
def pyramide():
    W, H = 860, 520
    layers = [
        ("Tests E2E navigateur", "0 exécuté (outil absent)", 250, "#dc2626"),
        ("Tests frontend (Karma)", "33 tests — 33 réussis", 360, "#f59e0b"),
        ("Tests d'intégration / sécurité / IA", "110 tests — 110 réussis", 480, "#3b82f6"),
        ("Tests unitaires (règles métier)", "50 tests — 50 réussis", 600, "#16a34a"),
    ]
    body = [f'<text x="{W/2}" y="36" text-anchor="middle" font-size="20" font-weight="bold">'
            f'Pyramide des tests — 193 tests automatisés exécutés</text>']
    y = 70
    for i, (titre, sous, w, color) in enumerate(layers):
        h = 88
        x = (W - w) / 2
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{color}" opacity="0.92"/>')
        body.append(f'<text x="{W/2}" y="{y+36}" text-anchor="middle" font-size="15" fill="#fff" font-weight="bold">{titre}</text>')
        body.append(f'<text x="{W/2}" y="{y+60}" text-anchor="middle" font-size="12" fill="#fff">{sous}</text>')
        y += h + 12
    return svg(W, H, "".join(body))


# ── Figure 3 : latences p50/p95/p99 selon la charge ────────────────────────
def performance():
    W, H = 780, 440
    labels = ["p50", "p95", "p99"]
    cinq = [137.85, 297.22, 365.90]
    dix = [261.58, 530.89, 637.03]
    max_val = 700
    left, top, bottom = 80, 70, 340
    group_w = (W - left - 40) / 3
    body = [f'<text x="{W/2}" y="36" text-anchor="middle" font-size="18" font-weight="bold">'
            f'Latence des API de lecture selon la charge (local)</text>']
    for i, lab in enumerate(labels):
        cx = left + group_w * i + group_w / 2
        for j, (val, color) in enumerate(((cinq[i], "#3b82f6"), (dix[i], "#1e40af"))):
            h = (val / max_val) * (bottom - top)
            x = cx - 34 + j * 36
            body.append(f'<rect x="{x}" y="{bottom-h}" width="30" height="{h}" fill="{color}" rx="4"/>')
            body.append(f'<text x="{x+15}" y="{bottom-h-6}" text-anchor="middle" font-size="10">{val:.0f}</text>')
        body.append(f'<text x="{cx}" y="{bottom+20}" text-anchor="middle" font-size="12" font-weight="bold">{lab}</text>')
    body.append(f'<line x1="{left}" y1="{bottom}" x2="{W-30}" y2="{bottom}" stroke="#9ca3af"/>')
    body.append(f'<rect x="{left}" y="{H-38}" width="12" height="12" fill="#3b82f6"/>'
                f'<text x="{left+18}" y="{H-28}" font-size="11">5 utilisateurs — 32,2 req/s</text>')
    body.append(f'<rect x="{left+230}" y="{H-38}" width="12" height="12" fill="#1e40af"/>'
                f'<text x="{left+248}" y="{H-28}" font-size="11">10 utilisateurs — 32,1 req/s</text>')
    return svg(W, H, "".join(body))


# ── Figure 4 : pipeline CI ─────────────────────────────────────────────────
def ci():
    W, H = 980, 240
    etapes = [
        ("Push", "main", "#6b7280"),
        ("Check", "Django", "#3b82f6"),
        ("Tests", "160 + 33", "#16a34a"),
        ("Couverture", "coverage.py", "#f59e0b"),
        ("Artefact", "rapport", "#8b5cf6"),
        ("Déploiement", "FTP + cron", "#0ea5e9"),
    ]
    body = [f'<text x="{W/2}" y="34" text-anchor="middle" font-size="18" font-weight="bold">'
            f'Pipeline d’intégration continue (GitHub Actions)</text>']
    bw, bh, gap = 130, 74, 22
    total = len(etapes) * bw + (len(etapes) - 1) * gap
    x = (W - total) / 2
    for i, (titre, sous, color) in enumerate(etapes):
        body.append(f'<rect x="{x}" y="90" width="{bw}" height="{bh}" rx="10" fill="{color}"/>')
        body.append(f'<text x="{x+bw/2}" y="120" text-anchor="middle" font-size="13" fill="#fff" font-weight="bold">{titre}</text>')
        body.append(f'<text x="{x+bw/2}" y="142" text-anchor="middle" font-size="11" fill="#fff">{sous}</text>')
        if i < len(etapes) - 1:
            body.append(f'<path d="M {x+bw+2} 127 L {x+bw+gap-2} 127" stroke="#9ca3af" stroke-width="2" '
                        f'marker-end="url(#a)"/>')
        x += bw + gap
    body.append('<defs><marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
                '<path d="M0,0 L8,4 L0,8 z" fill="#9ca3af"/></marker></defs>')
    body.append(f'<text x="{W/2}" y="205" text-anchor="middle" font-size="11" fill="#6b7280">'
                f'Chaque push sur main exécute les tests puis déclenche le déploiement.</text>')
    return svg(W, H, "".join(body))


for nom, contenu in (
    ("couverture-modules.svg", couverture()),
    ("pyramide-tests.svg", pyramide()),
    ("performance-latence.svg", performance()),
    ("pipeline-ci.svg", ci()),
):
    (OUT / nom).write_text(contenu, encoding="utf-8")
    print("  ", OUT / nom)
