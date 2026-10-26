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

import base64
import csv
import html as _html
import io
import logging
import re
from types import SimpleNamespace

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
            item = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{_inline_md(item)}</li>")
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


def _heading_level(style: str, size_pt: float) -> int:
    st = (style or "").lower()
    m = re.match(r"heading\s*(\d)", st)
    if m:
        return max(1, min(6, int(m.group(1))))
    if st.startswith("title"):
        return 1
    if size_pt:
        if size_pt >= 22:
            return 1
        if size_pt >= 17:
            return 2
        if size_pt >= 14.5:
            return 3
        if size_pt >= 12.5:
            return 4
    return 0


def _align_class(alignment) -> str:
    try:
        v = int(alignment) if alignment is not None else None
    except Exception:
        return ""
    # WD_ALIGN_PARAGRAPH: 1=CENTER, 2=RIGHT, 3=JUSTIFY
    return {1: "doc-center", 2: "doc-right", 3: "doc-justify"}.get(v, "")


def _align_css(alignment) -> str:
    return {"doc-center": "center", "doc-right": "right", "doc-justify": "justify"}.get(
        _align_class(alignment), ""
    )


def _docx_family(name: str) -> str:
    f = (name or "").lower()
    if "courier" in f or "consolas" in f or "mono" in f:
        return f"{name}, monospace"
    if "times" in f or "georgia" in f or "garamond" in f or "cambria" in f:
        return f"{name}, Times, serif"
    return f"{name}, Arial, sans-serif"



def _style_font(style, normal_font=None):
    """Résout la chaîne de styles Word (base_style) + style Normal.

    Retourne un objet léger exposant name/size/color/bold/italic/underline.
    Word n'écrit que les propriétés surchargées : sans cette résolution, un
    texte hérité du style « Titre 1 » ou d'un style personnalisé perd sa police.
    """
    name = size = color = None
    bold = italic = underline = None
    seen = set()
    cur = style
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        try:
            f = cur.font
        except Exception:
            f = None
        if f is not None:
            try:
                if name is None and f.name:
                    name = f.name
                if size is None and f.size:
                    size = f.size
                if color is None and f.color and f.color.rgb:
                    color = f.color.rgb
                if bold is None and f.bold is not None:
                    bold = bool(f.bold)
                if italic is None and f.italic is not None:
                    italic = bool(f.italic)
                if underline is None and f.underline is not None:
                    underline = bool(f.underline)
            except Exception:
                pass
        cur = getattr(cur, "base_style", None)

    if normal_font is not None:
        try:
            if name is None and normal_font.name:
                name = normal_font.name
            if size is None and normal_font.size:
                size = normal_font.size
            if color is None and normal_font.color and normal_font.color.rgb:
                color = normal_font.color.rgb
        except Exception:
            pass

    return SimpleNamespace(
        name=name, size=size,
        color=SimpleNamespace(rgb=color) if color else None,
        bold=bool(bold) if bold is not None else False,
        italic=bool(italic) if italic is not None else False,
        underline=bool(underline) if underline is not None else False,
    )


def _docx_images(p, doc, max_bytes=2 * 1024 * 1024):
    """Extrait les images inline d'un paragraphe Word en data-URI.

    Les images sont auto-portées : l'aperçu éditable et la création depuis
    l'arborescence (JSON) les conservent sans dépendre d'un fichier média.
    """
    uris = []
    try:
        from docx.oxml.ns import qn
        blips = p._element.findall(".//" + qn("a:blip"))
    except Exception:
        return uris
    for blip in blips:
        try:
            rid = blip.get(qn("r:embed"))
            if not rid:
                continue
            part = doc.part.related_parts.get(rid)
            if part is None:
                continue
            blob = getattr(part, "blob", None)
            if not blob or len(blob) > max_bytes:
                continue
            mime = getattr(part, "content_type", None) or "image/png"
            uris.append(f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}")
        except Exception:
            continue
    return uris


def _images_html(uris):
    return "".join(
        f'<p style="text-align:center;margin:8px 0;">'
        f'<img src="{u}" alt="Image du document" style="max-width:100%;height:auto;" />'
        f'</p>'
        for u in uris
    )

def _run_style(r, base=None) -> str:
    """Style inline d'un run Word : police, taille, couleur, gras/italique/souligné.
    `base` = police héritée du style de paragraphe / style Normal."""
    st = []
    try:
        f = r.font
        name = (f.name if f is not None else None) or (base.name if base is not None else None)
        if name:
            st.append(f"font-family:{_docx_family(name)}")
        size = None
        if f is not None and f.size:
            try:
                size = float(f.size.pt)
            except Exception:
                size = None
        if size is None and base is not None and base.size:
            try:
                size = float(base.size.pt)
            except Exception:
                size = None
        if size:
            st.append(f"font-size:{size}pt")
        color = None
        try:
            if f is not None and f.color and f.color.rgb:
                color = f"#{f.color.rgb}"
        except Exception:
            color = None
        if color is None:
            try:
                if base is not None and base.color and base.color.rgb:
                    color = f"#{base.color.rgb}"
            except Exception:
                color = None
        if color:
            st.append(f"color:{color}")
    except Exception:
        pass
    bold = r.bold if r.bold is not None else getattr(base, "bold", False)
    italic = r.italic if r.italic is not None else getattr(base, "italic", False)
    underline = getattr(r, "underline", None)
    if underline is None:
        underline = getattr(base, "underline", False)
    if bold:
        st.append("font-weight:700")
    if italic:
        st.append("font-style:italic")
    if underline:
        st.append("text-decoration:underline")
    return ";".join(st)


def _docx_to_blocs(data):
    """Convertit un document Word en blocs HTML en s'appuyant sur la mise en forme
    réelle (styles, taille de police, gras/italique/souligné, alignement)."""
    import docx
    d = docx.Document(io.BytesIO(data))
    try:
        normal_font = d.styles["Normal"].font
    except Exception:
        normal_font = None
    blocs = []
    cur = None

    def _new(titre):
        nonlocal cur
        cur = {"ordre": len(blocs) + 1, "titre": titre, "type_bloc": "html", "contenu": "",
               "url": "", "est_obligatoire": True, "est_visible": True}
        blocs.append(cur)

    def _runs_html(p, base=None):
        parts = []
        for r in p.runs:
            s = _html.escape(r.text or "")
            if not s:
                continue
            style = _run_style(r, base)
            if style:
                parts.append(f'<span style="{style}">{s}</span>')
            else:
                parts.append(s)
        return "".join(parts) or _html.escape((p.text or "").strip())

    def _size(p):
        sizes = []
        for r in p.runs:
            try:
                if r.font and r.font.size:
                    sizes.append(float(r.font.size.pt))
            except Exception:
                pass
        return max(sizes) if sizes else 0.0

    for p in d.paragraphs:
        txt = (p.text or "").strip()
        images = _docx_images(p, d)
        if not txt:
            if images:
                if cur is None:
                    _new("Images")
                cur["contenu"] += _images_html(images) + "\n"
            continue
        style = (p.style.name if p.style else "") or ""
        level = _heading_level(style, _size(p))

        align_css = _align_css(getattr(p, "alignment", None))
        style_attr = f' style="text-align:{align_css}"' if align_css else ""

        base_font = _style_font(p.style if p.style else None, normal_font)

        if level:
            _new(txt)
            cur["contenu"] = f"<h{level}{style_attr}>{_runs_html(p, base_font)}</h{level}>\n"
            continue

        if cur is None:
            _new("Introduction")
        st = style.lower()
        inner = _runs_html(p, base_font)
        if st.startswith("list bullet"):
            inner = f"<ul><li>{inner}</li></ul>"
        elif st.startswith("list number"):
            inner = f"<ol><li>{inner}</li></ol>"
        elif "code" in st:
            inner = f"<pre><code>{_html.escape(txt)}</code></pre>"
        else:
            inner = f"<p{style_attr}>{inner}</p>"
        cur["contenu"] += inner + (_images_html(images) if images else "") + "\n"

    for table in d.tables:
        if cur is None:
            _new("Tableau")
        rows = "".join(
            "<tr>" + "".join(
                f'<td style="border:1px solid #CBD5E1;padding:4px 6px;">{_html.escape(c.text)}</td>'
                for c in row.cells
            ) + "</tr>"
            for row in table.rows
        )
        cur["contenu"] += f'<table style="border-collapse:collapse;width:100%;margin:8px 0;">{rows}</table>\n'

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
        try:
            from .pdf_style import pdf_to_blocs
            blocs = pdf_to_blocs(data)
        except Exception as exc:
            _warn(f"Extraction PDF stylée impossible ({exc}) → repli en texte.")
            blocs = []
        if not blocs or not any((b.get("contenu") or "").strip() for b in blocs):
            text = _read_pdf(data)
            if not (text or "").strip():
                try:
                    from . import ocr
                    if ocr.disponible():
                        text = ocr.ocr_pdf(data)
                        if text.strip():
                            _warn("PDF scanné : texte extrait par OCR (mise en forme approximative).")
                except Exception as exc:
                    _warn(f"OCR du PDF impossible ({exc}).")
            blocs = _text_to_blocs(text, base)
    elif name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        try:
            from . import ocr
            if ocr.disponible():
                text = ocr.ocr_image(data)
                blocs = _text_to_blocs(text, base)
                if blocs:
                    _warn("Image : texte extrait par OCR (mise en forme approximative).")
            else:
                _warn("OCR indisponible : installez tesseract-ocr et pytesseract.")
                blocs = []
        except Exception as exc:
            _warn(f"OCR de l'image impossible ({exc}).")
            blocs = []
    else:
        _warn("Format non pris en charge (.xlsx, .csv, .docx, .pdf, images, .txt).")
        blocs = []

    return {"blocs": blocs, "warnings": list(_WARN), "nb": len(blocs)}
