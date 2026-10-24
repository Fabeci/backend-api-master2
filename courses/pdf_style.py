# courses/pdf_style.py
# =============================================================================
# Extraction d'un PDF en HTML FIDÈLE : polices, tailles, couleurs, gras/italique,
# alignement, liens. Utilise `pdfplumber` (informations de police par caractère).
# =============================================================================

import html
import io
import logging
import re
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

_BOLD = re.compile(r"(bold|black|heavy|semibold|demi)", re.I)
_ITALIC = re.compile(r"(italic|oblique)", re.I)


def _color(c):
    if c is None:
        return None
    if isinstance(c, (list, tuple)):
        if len(c) == 1:
            v = max(0, min(255, int(c[0] * 255)))
            return f"rgb({v},{v},{v})"
        if len(c) == 3:
            r, g, b = (max(0, min(255, int(x * 255))) for x in c)
            return f"rgb({r},{g},{b})"
        if len(c) == 4:
            cy, m, y, k = c
            r = (1 - cy) * (1 - k)
            g = (1 - m) * (1 - k)
            b = (1 - y) * (1 - k)
            return f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"
    if isinstance(c, (int, float)):
        v = max(0, min(255, int(c * 255)))
        return f"rgb({v},{v},{v})"
    return None


def _family(fontname):
    f = (fontname or "").lower()
    if "courier" in f or "mono" in f:
        return "Courier New, monospace"
    if "times" in f or "serif" in f:
        return "Times New Roman, Times, serif"
    if "georgia" in f:
        return "Georgia, serif"
    if "calibri" in f:
        return "Calibri, Arial, sans-serif"
    return "Arial, Helvetica, sans-serif"


def _lines(chars, tolerance=2.5):
    """Regroupe les caractères par ligne (y)."""
    buckets = []
    for ch in sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"])):
        placed = False
        for b in buckets:
            if abs(b["top"] - ch["top"]) <= tolerance:
                b["chars"].append(ch)
                b["top"] = min(b["top"], ch["top"])
                placed = True
                break
        if not placed:
            buckets.append({"top": ch["top"], "chars": [ch]})
    buckets.sort(key=lambda b: b["top"])
    return [sorted(b["chars"], key=lambda c: c["x0"]) for b in buckets]


def _with_spaces(chars):
    """Reconstruit les espaces à partir des écarts horizontaux (certains PDF
    n'incluent pas de caractère espace)."""
    chars = sorted(chars, key=lambda c: c["x0"])
    processed = []
    prev = None
    for ch in chars:
        if prev is not None:
            gap = float(ch["x0"]) - float(prev.get("x1") or ch["x0"])
            threshold = 0.18 * max(float(prev.get("size") or 10), 6)
            if gap > threshold and (not processed or not str(processed[-1].get("text", "")).endswith(" ")):
                processed.append({**ch, "text": " ", "x0": ch["x0"], "x1": ch["x0"]})
        processed.append(ch)
        prev = ch
    return processed


def _align_of(x0, x1, page_width):
    width = x1 - x0
    center = (x0 + x1) / 2
    if width < page_width * 0.75 and abs(center - page_width / 2) < page_width * 0.12:
        return "center"
    if x0 > page_width * 0.55 and width < page_width * 0.45:
        return "right"
    return "left"


def _line_html(chars, page_width, links):
    if not chars:
        return ""

    # Reconstruction des espaces à partir des écarts horizontaux (certains PDF
    # n'incluent pas de caractère espace).
    chars = _with_spaces(chars)

    # Regroupement en « runs » de même police/taille/couleur
    runs = []
    for ch in chars:
        key = (ch.get("fontname"), round(float(ch.get("size") or 0), 1), _color(ch.get("non_stroking_color")))
        if runs and runs[-1]["key"] == key:
            runs[-1]["text"] += ch.get("text", "")
        else:
            runs.append({"key": key, "text": ch.get("text", "")})

    sizes = [float(c.get("size") or 0) for c in chars]
    fonts = [c.get("fontname") for c in chars]
    colors = [_color(c.get("non_stroking_color")) for c in chars]
    size = Counter(round(s, 1) for s in sizes).most_common(1)[0][0] if sizes else 11
    font = Counter(fonts).most_common(1)[0][0]
    color = Counter(colors).most_common(1)[0][0]

    x0 = min(c["x0"] for c in chars)
    x1 = max(c["x1"] for c in chars)
    align = _align_of(x0, x1, page_width)

    p_style = f"font-family:{_family(font)};font-size:{size}pt;text-align:{align};"
    if color:
        p_style += f"color:{color};"
    if _BOLD.search(font or ""):
        p_style += "font-weight:700;"
    if _ITALIC.search(font or ""):
        p_style += "font-style:italic;"

    spans = []
    for r in runs:
        f, s, c = r["key"]
        st = f"font-family:{_family(f)};font-size:{s}pt;"
        if c:
            st += f"color:{c};"
        if _BOLD.search(f or ""):
            st += "font-weight:700;"
        if _ITALIC.search(f or ""):
            st += "font-style:italic;"
        spans.append(f'<span style="{st}">{html.escape(r["text"])}</span>')
    inner = "".join(spans) or html.escape("".join(c.get("text", "") for c in chars))

    # Lien : si la ligne tombe dans la bbox d'un hyperlien
    top = chars[0]["top"]
    href = None
    for link in links:
        try:
            if (link.get("x0", 0) - 3 <= x0 and x1 <= link.get("x1", 0) + 3
                    and link.get("top", 0) - 3 <= top <= link.get("bottom", 0) + 3):
                href = link.get("uri") or link.get("url")
                break
        except Exception:
            continue
    if href:
        inner = f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{inner}</a>'

    return f'<p style="{p_style}">{inner}</p>'


def pdf_to_blocs(data: bytes) -> list[dict]:
    """Retourne un bloc HTML par page, en conservant le design du PDF."""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber n'est pas installé.")

    blocs = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        meta = pdf.metadata or {}
        titre_doc = (meta.get("Title") or "").strip() or "Document importé"

        for idx, page in enumerate(pdf.pages, start=1):
            try:
                page_width = float(page.width)
            except Exception:
                page_width = 595.0
            chars = [c for c in (page.chars or []) if (c.get("text") or "").strip()]
            links = list(getattr(page, "hyperlinks", []) or [])

            parts = []
            for line in _lines(chars):
                h = _line_html(line, page_width, links)
                if h:
                    parts.append(h)

            # Tableaux (optionnel) : rendu simple si présents
            try:
                for table in (page.extract_tables() or []):
                    if not table:
                        continue
                    rows = []
                    for row in table:
                        cells = "".join(
                            f'<td style="border:1px solid #CBD5E1;padding:4px 6px;">{html.escape(str(c or ""))}</td>'
                            for c in row
                        )
                        rows.append(f"<tr>{cells}</tr>")
                    parts.append(
                        '<table style="border-collapse:collapse;width:100%;margin:8px 0;">'
                        + "".join(rows) + "</table>"
                    )
            except Exception:
                pass

            if not parts:
                continue

            blocs.append({
                "ordre": idx,
                "titre": f"{titre_doc} — page {idx}" if len(pdf.pages) > 1 else titre_doc,
                "type_bloc": "html",
                "contenu": "\n".join(parts),
                "url": "",
                "est_obligatoire": True,
                "est_visible": True,
            })

    return blocs


def pdf_lines(data: bytes) -> dict:
    """Lignes de chaque page avec métadonnées de style (police, taille, couleur,
    alignement, gras/italique) — base de l'import d'un cours complet.

    Retour : {"titre": str, "pages": [{"page", "width", "lines": [...]}]}
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber n'est pas installé.")

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        meta = pdf.metadata or {}
        titre = (meta.get("Title") or "").strip()
        for idx, page in enumerate(pdf.pages, start=1):
            try:
                width = float(page.width)
            except Exception:
                width = 595.0
            chars = [c for c in (page.chars or []) if (c.get("text") or "").strip()]
            links = list(getattr(page, "hyperlinks", []) or [])
            out = []
            for raw in _lines(chars):
                text = "".join(c.get("text", "") for c in _with_spaces(raw)).strip()
                if not text:
                    continue
                sizes = [float(c.get("size") or 0) for c in raw]
                size = Counter(round(s, 1) for s in sizes).most_common(1)[0][0] if sizes else 11.0
                font = Counter([c.get("fontname") for c in raw]).most_common(1)[0][0]
                colors = [_color(c.get("non_stroking_color")) for c in raw]
                color = Counter(colors).most_common(1)[0][0]
                x0 = min(c["x0"] for c in raw)
                x1 = max(c["x1"] for c in raw)
                html = _line_html(raw, width, links)
                inner = re.sub(r"^<p[^>]*>", "", html)
                inner = re.sub(r"</p>$", "", inner)
                out.append({
                    "text": text,
                    "inner": inner,
                    "size": size,
                    "font": font,
                    "bold": bool(_BOLD.search(font or "")),
                    "italic": bool(_ITALIC.search(font or "")),
                    "color": color,
                    "align": _align_of(x0, x1, width),
                    "top": float(min(c["top"] for c in raw)),
                    "bottom": float(max(c.get("bottom", c["top"]) for c in raw)),
                })
            pages.append({"page": idx, "width": width, "lines": out})
    return {"titre": titre, "pages": pages}
