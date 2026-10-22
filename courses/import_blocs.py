# courses/import_blocs.py
# =============================================================================
# Extraction de BLOCS DE CONTENU depuis un fichier (Excel, CSV, Word, PDF, TXT).
#
# Modes :
#   1) STRUCTURÉ (xlsx, csv) : colonnes (ordre, titre, type_bloc, contenu, url,
#      obligatoire, visible).
#   2) TEXTE (txt, docx, pdf) : titres (# Titre / « Titre : » / « Bloc n: »),
#      corps = paragraphes suivants ; ``` pour un bloc de code.
#
# Sortie : { blocs: [ {ordre,titre,type_bloc,contenu,url,est_obligatoire,est_visible} ],
#            warnings: [str], nb: int }
# =============================================================================

import csv
import html as _html
import io
import logging
import re

logger = logging.getLogger(__name__)

TYPES = {"texte", "html", "markdown", "video", "audio", "image", "fichier", "lien", "code"}
_WARN = []

_MD = re.compile(r"(^#{1,6}\s|\*\*[^*]+\*\*|^\s*[-*]\s+|```)", re.M)
_HTML = re.compile(r"<(p|h[1-6]|ul|ol|li|strong|em|b|i|table|div|br)\b", re.I)


def _looks_markdown(t: str) -> bool:
    return bool(_MD.search(t or ""))


def _looks_html(t: str) -> bool:
    return bool(_HTML.search(t or ""))


def _inline_md(s: str) -> str:
    s = _html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _md_to_html(t: str) -> str:
    """Convertisseur Markdown minimal → HTML (titres, gras/italique, listes, code)."""
    lines = (t or "").replace("\r\n", "\n").split("\n")
    out, in_code, in_list = [], False, False
    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            out.append(_html.escape(line))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline_md(m.group(2))}</h{lvl}>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_md(re.sub(r'^\s*[-*]\s+', '', line))}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.strip():
            out.append(f"<p>{_inline_md(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _text_to_html(t: str) -> str:
    """Texte brut → HTML (paragraphes + sauts de ligne préservés)."""
    t = (t or "").replace("\r\n", "\n").strip()
    if not t:
        return ""
    paras = re.split(r"\n\s*\n", t)
    return "\n".join(f"<p>{_html.escape(p).replace(chr(10), '<br>')}</p>" for p in paras if p.strip())


def _warn(m):
    _WARN.append(m)


_COL = {
    "ordre": "ordre", "order": "ordre", "n": "ordre", "numero": "ordre", "position": "ordre",
    "titre": "titre", "title": "titre", "nom": "titre", "libelle": "titre", "heading": "titre",
    "bloc": "titre", "sous_titre": "titre", "intitule": "titre",
    "type": "type", "type_bloc": "type", "type_contenu": "type",
    "contenu": "contenu", "content": "contenu", "texte": "contenu", "corps": "contenu",
    "description": "contenu", "body": "contenu", "value": "contenu",
    "url": "url", "lien": "url", "link": "url", "video": "url",
    "obligatoire": "obligatoire", "required": "obligatoire",
    "visible": "visible", "visibilite": "visible",
}


def _norm(h):
    h = (h or "").strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ç", "c"), ("ô", "o")):
        h = h.replace(a, b)
    return re.sub(r"[\s\-]+", "_", h)


def _bool(v, default=True):
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "vrai", "oui", "yes", "x", "actif", "visible")


def _rows_to_blocs(rows):
    if not rows:
        return []
    header = [_norm(str(c)) for c in rows[0]]
    idx = {}
    for i, h in enumerate(header):
        key = _COL.get(h)
        if key:
            idx.setdefault(key, i)
    if "titre" not in idx:
        # Tolérance : pas d'entête « titre » → on prend la 1re colonne comme titre
        # et la 2e comme contenu (best effort).
        _warn("Colonne « titre » introuvable dans l'entête : la 1re colonne sera utilisée comme titre.")
        idx = {"titre": 0, "contenu": 1} if len(header) >= 2 else {"titre": 0}

    blocs = []
    for r, row in enumerate(rows[1:], start=2):
        def cell(k, d=""):
            i = idx.get(k)
            return (str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else d)

        titre = cell("titre")
        if not titre:
            continue
        type_bloc = (cell("type") or "texte").strip().lower()
        if type_bloc not in TYPES:
            _warn(f"Ligne {r} : type « {type_bloc} » inconnu → 'texte'.")
            type_bloc = "texte"
        contenu = cell("contenu")
        # Auto-détection : si le type n'est pas précisé, on respecte le contenu.
        if type_bloc == "texte" and contenu:
            if _looks_html(contenu):
                type_bloc = "html"
            elif _looks_markdown(contenu):
                contenu = _md_to_html(contenu)
                type_bloc = "html"
        try:
            ordre = int(cell("ordre", str(len(blocs) + 1)))
        except Exception:
            ordre = len(blocs) + 1
        blocs.append({
            "ordre": ordre,
            "titre": titre,
            "type_bloc": type_bloc,
            "contenu": contenu,
            "url": cell("url"),
            "est_obligatoire": _bool(cell("obligatoire"), True),
            "est_visible": _bool(cell("visible"), True),
        })
    return blocs


def _parse_text(text):
    """Heuristique : titres '#'/'Titre :'/'Bloc n,' puis corps."""
    blocs = []
    cur = None
    in_code = False
    code_buf = []

    def flush():
        nonlocal cur
        if cur is not None:
            cur["contenu"] = cur["contenu"].strip()
            blocs.append(cur)
            cur = None

    for line in text.splitlines():
        s = line.rstrip()
        if s.strip().startswith("```"):
            if cur is None:
                cur = {"titre": "Bloc de code", "type_bloc": "code", "contenu": "", "url": "", "ordre": len(blocs) + 1, "est_obligatoire": True, "est_visible": True}
            in_code = not in_code
            cur["type_bloc"] = "code"
            continue
        if in_code:
            cur["contenu"] += line + "\n"
            continue

        m = re.match(r"^\s*(?:#+\s*|bloc\s*\d+\s*[:\-\.]\s*|titre\s*[:\-]\s*)(.+)$", s, re.IGNORECASE)
        if m and len(s.strip()) < 160:
            flush()
            cur = {"titre": m.group(1).strip(), "type_bloc": "texte", "contenu": "", "url": "", "ordre": len(blocs) + 1, "est_obligatoire": True, "est_visible": True}
            continue
        if cur is None:
            continue
        cur["contenu"] += s + "\n"

    flush()
    return blocs


def _parse_xlsx(data):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    return _rows_to_blocs([list(r) for r in wb.active.iter_rows(values_only=True)])


def _parse_csv(data):
    text = data.decode("utf-8-sig", errors="ignore")
    delim = ";" if text[:2000].count(";") > text[:2000].count(",") else ","
    return _rows_to_blocs([row for row in csv.reader(io.StringIO(text), delimiter=delim)])


def _read_docx(data):
    import docx
    d = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in d.paragraphs)


def _read_pdf(data):
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def _docx_to_blocs(data):
    """Convertit un document Word en blocs HTML (titres, gras/italique, listes, tableaux)."""
    import docx
    d = docx.Document(io.BytesIO(data))
    blocs = []
    cur = None

    def _new(titre):
        nonlocal cur
        cur = {"ordre": len(blocs) + 1, "titre": titre, "type_bloc": "html", "contenu": "",
               "url": "", "est_obligatoire": True, "est_visible": True}
        blocs.append(cur)

    for p in d.paragraphs:
        txt = (p.text or "").strip()
        if not txt:
            continue
        style = ((p.style.name if p.style else "") or "").lower()
        if style.startswith(("heading", "title", "titre")):
            _new(txt)
            continue
        if cur is None:
            _new("Introduction")
        parts = []
        for r in p.runs:
            s = _html.escape(r.text or "")
            if not s:
                continue
            if r.bold:
                s = f"<strong>{s}</strong>"
            if r.italic:
                s = f"<em>{s}</em>"
            if getattr(r, "underline", False):
                s = f"<u>{s}</u>"
            parts.append(s)
        inner = "".join(parts) or _html.escape(txt)
        if style.startswith("list bullet"):
            inner = f"<ul><li>{inner}</li></ul>"
        elif style.startswith("list number"):
            inner = f"<ol><li>{inner}</li></ol>"
        elif "code" in style:
            inner = f"<pre><code>{_html.escape(txt)}</code></pre>"
        else:
            inner = f"<p>{inner}</p>"
        cur["contenu"] += inner + "\n"

    for table in d.tables:
        if cur is None:
            _new("Tableau")
        rows = "".join(
            "<tr>" + "".join(f"<td>{_html.escape(c.text)}</td>" for c in row.cells) + "</tr>"
            for row in table.rows
        )
        cur["contenu"] += f"<table>{rows}</table>\n"

    return blocs


def _text_to_blocs(text, fallback_title):
    """TXT/PDF : on produit du HTML (paragraphes ; Markdown converti en HTML)."""
    md = _looks_markdown(text)
    blocs = _parse_text(text)
    if not blocs:
        if not (text or "").strip():
            return []
        return [{
            "ordre": 1,
            "titre": fallback_title or "Contenu importé",
            "type_bloc": "html",
            "contenu": _md_to_html(text) if md else _text_to_html(text),
            "url": "", "est_obligatoire": True, "est_visible": True,
        }]
    for b in blocs:
        b["contenu"] = _md_to_html(b["contenu"]) if md else _text_to_html(b["contenu"])
        b["type_bloc"] = "html"
    return blocs


def extract_blocs(filename: str, data: bytes) -> dict:
    _WARN.clear()
    name = (filename or "").lower()
    import os as _os
    base = _os.path.splitext(_os.path.basename(filename or ""))[0]

    if name.endswith((".xlsx", ".xlsm")):
        blocs = _parse_xlsx(data)
    elif name.endswith(".csv"):
        blocs = _parse_csv(data)
    elif name.endswith(".docx"):
        blocs = _docx_to_blocs(data)
    elif name.endswith(".txt"):
        blocs = _text_to_blocs(data.decode("utf-8-sig", errors="ignore"), base)
    elif name.endswith(".pdf"):
        blocs = _text_to_blocs(_read_pdf(data), base)
    else:
        _warn("Format non pris en charge (.xlsx, .csv, .docx, .pdf, .txt).")
        blocs = []

    return {"blocs": blocs, "warnings": list(_WARN), "nb": len(blocs)}
