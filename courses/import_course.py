# courses/import_course.py
# =============================================================================
# Import d'un COURS COMPLET depuis un document Word (.docx) ou PDF :
#   modules → séquences → blocs (+ quiz et leurs questions/réponses).
#
# La mise en forme du document source est conservée (polices, tailles,
# couleurs, gras/italique, alignement) sous forme de styles inline.
# =============================================================================

import html as _html
import io
import logging
import os
import re
from collections import Counter

from courses import import_blocs, pdf_style

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Détection des titres structurels
# ─────────────────────────────────────────────────────────────────────────────

_KIND_RX = [
    ("module", re.compile(r"^(module|partie|unit[ée])\b", re.I)),
    ("sequence", re.compile(r"^(s[ée]quence|chapitre)\b", re.I)),
    ("bloc", re.compile(r"^(bloc|section|le[çc]on)\b", re.I)),
    ("quiz", re.compile(r"^(quiz|qcm|[ée]valuation|evaluation|test)\b", re.I)),
]


def _kind_of(title: str, is_heading: bool = False):
    """Retourne module/sequence/bloc/quiz si le texte commence par un mot-clé.

    En dehors d'un vrai titre, on exige un numéro ou un séparateur juste après
    le mot-clé (pour ne pas transformer « Module de gestion » en module).
    """
    t = re.sub(r"\s+", " ", (title or "")).strip()
    low = t.lower()
    for kind, rx in _KIND_RX:
        m = rx.match(low)
        if not m:
            continue
        rest = low[m.end():]
        if is_heading or not rest.strip() or re.match(r"^\s*(\d+|[:\-–—.])", rest):
            return kind
    return None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _similar(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) > len(nb):
        return na.startswith(nb) and len(nb) >= 0.8 * len(na)
    return nb.startswith(na) and len(na) >= 0.8 * len(nb)


# ─────────────────────────────────────────────────────────────────────────────
# Constructeur de l'arborescence
# ─────────────────────────────────────────────────────────────────────────────

class _Builder:
    def __init__(self, titre: str, skip_preamble: bool = False):
        self.titre = (titre or "Cours importé").strip()
        self.modules: list[dict] = []
        self.cur_module = None
        self.cur_seq = None
        self.cur_bloc = None
        self.cur_quiz = None
        self.warnings: list[str] = []
        self._first_heading = True
        self.skip_preamble = skip_preamble
        self.preamble: list[str] = []

    # ── niveaux implicites ────────────────────────────────────────────────
    def _ensure_module(self):
        if self.cur_module is None:
            m = {
                "titre": f"Module {len(self.modules) + 1}",
                "description": "",
                "ordre": len(self.modules) + 1,
                "sequences": [],
            }
            self.modules.append(m)
            self.cur_module = m

    def _ensure_sequence(self):
        self._ensure_module()
        if self.cur_seq is None:
            s = {
                "titre": "Introduction",
                "description": "",
                "ordre": len(self.cur_module["sequences"]) + 1,
                "blocs": [],
                "quizzes": [],
            }
            self.cur_module["sequences"].append(s)
            self.cur_seq = s

    def _ensure_bloc(self):
        self._ensure_sequence()
        if self.cur_bloc is None:
            b = {
                "titre": "Contenu",
                "ordre": len(self.cur_seq["blocs"]) + 1,
                "type_bloc": "html",
                "contenu": "",
                "url": "",
                "est_obligatoire": True,
                "est_visible": True,
            }
            self.cur_seq["blocs"].append(b)
            self.cur_bloc = b
        return self.cur_bloc

    # ── titres ────────────────────────────────────────────────────────────
    def heading(self, kind: str, titre: str):
        titre = re.sub(r"\s+", " ", (titre or "")).strip()
        self.cur_bloc = None

        if kind == "module":
            self.cur_quiz = None
            self.cur_seq = None
            m = {
                "titre": titre or f"Module {len(self.modules) + 1}",
                "description": "",
                "ordre": len(self.modules) + 1,
                "sequences": [],
            }
            self.modules.append(m)
            self.cur_module = m

        elif kind == "sequence":
            self.cur_quiz = None
            self._ensure_module()
            s = {
                "titre": titre or f"Séquence {len(self.cur_module['sequences']) + 1}",
                "description": "",
                "ordre": len(self.cur_module["sequences"]) + 1,
                "blocs": [],
                "quizzes": [],
            }
            self.cur_module["sequences"].append(s)
            self.cur_seq = s

        elif kind == "bloc":
            self.cur_quiz = None
            self._ensure_sequence()
            b = {
                "titre": titre or f"Bloc {len(self.cur_seq['blocs']) + 1}",
                "ordre": len(self.cur_seq["blocs"]) + 1,
                "type_bloc": "html",
                "contenu": "",
                "url": "",
                "est_obligatoire": True,
                "est_visible": True,
            }
            self.cur_seq["blocs"].append(b)
            self.cur_bloc = b

        elif kind == "quiz":
            self._ensure_sequence()
            q = {"titre": titre or "Quiz", "description": "", "_text": "", "questions": []}
            self.cur_seq["quizzes"].append(q)
            self.cur_quiz = q

    # ── contenu ───────────────────────────────────────────────────────────
    def add_content(self, html: str, text: str = ""):
        if self.cur_quiz is not None:
            if text:
                self.cur_quiz["_text"] += text + "\n"
            return
        # Contenu avant le premier titre (page de garde…) : ce n'est pas un module.
        if self.skip_preamble and self.cur_module is None and not self.modules:
            if text:
                self.preamble.append(text)
            return
        b = self._ensure_bloc()
        b["contenu"] += (html or "") + "\n"

    # ── finalisation ──────────────────────────────────────────────────────
    def finish(self) -> dict:
        from evaluations.import_questions import _parse_text as parse_questions

        for m in self.modules:
            for s in m["sequences"]:
                for q in s["quizzes"]:
                    raw = q.pop("_text", "")
                    questions = parse_questions(raw) if raw.strip() else []
                    q["questions"] = questions
                    if not questions:
                        self.warnings.append(
                            f"Quiz « {q['titre']} » : aucune question reconnue "
                            "(format attendu : « Question 1 », options « a) … », « Réponse : b »)."
                        )

        # Nettoyage des niveaux vides.
        self.modules = [m for m in self.modules if m["sequences"]]
        for m in self.modules:
            m["sequences"] = [s for s in m["sequences"] if s["blocs"] or s["quizzes"]]

        # Renumérotation.
        for mi, m in enumerate(self.modules, start=1):
            m["ordre"] = mi
            for si, s in enumerate(m["sequences"], start=1):
                s["ordre"] = si
                for bi, b in enumerate(s["blocs"], start=1):
                    b["ordre"] = bi

        stats = {
            "modules": len(self.modules),
            "sequences": sum(len(m["sequences"]) for m in self.modules),
            "blocs": sum(len(s["blocs"]) for m in self.modules for s in m["sequences"]),
            "quizzes": sum(len(s["quizzes"]) for m in self.modules for s in m["sequences"]),
            "questions": sum(
                len(q["questions"]) for m in self.modules for s in m["sequences"] for q in s["quizzes"]
            ),
        }
        if not self.modules:
            self.warnings.append("Aucune structure détectée : vérifiez que le document contient des titres.")

        return {
            "titre": self.titre,
            "modules": self.modules,
            "stats": stats,
            "warnings": self.warnings,
        }


# ─────────────────────────────────────────────────────────────────────────────
# WORD
# ─────────────────────────────────────────────────────────────────────────────

def _para_size(p) -> float:
    sizes = []
    for r in p.runs:
        try:
            if r.font and r.font.size:
                sizes.append(float(r.font.size.pt))
        except Exception:
            pass
    return max(sizes) if sizes else 0.0


def _docx_heading(p, normal_font) -> int:
    """Niveau de titre fiable : style Word, ou taille DOMINANTE du paragraphe.

    Un simple mot mis en valeur (13 pt) dans un paragraphe de 11 pt ne doit pas
    transformer tout le paragraphe en titre.
    """
    style = (p.style.name if p.style else "") or ""
    st = style.lower()

    m = re.match(r"heading\s*(\d)", st)
    if m:
        return max(1, min(6, int(m.group(1))))
    if st.startswith("title"):
        return 1

    base = 11.0
    try:
        if normal_font is not None and normal_font.size:
            base = float(normal_font.size.pt)
    except Exception:
        pass

    sizes = []
    for r in p.runs:
        if not (r.text or "").strip():
            continue
        try:
            sizes.append(float(r.font.size.pt) if r.font and r.font.size else base)
        except Exception:
            sizes.append(base)
    if not sizes:
        return 0

    dominant, count = Counter(round(s, 1) for s in sizes).most_common(1)[0]
    if count < 0.6 * len(sizes):
        return 0
    if len((p.text or "").strip()) > 120:
        return 0

    if dominant >= 22:
        return 1
    if dominant >= 17:
        return 2
    if dominant >= 14.5:
        return 3
    return 0


def _base_font(p, normal_font):
    """Police effective : style du paragraphe → chaîne base_style → Normal."""
    return import_blocs._style_font(p.style if p.style else None, normal_font)


def _runs_inner(p, base) -> str:
    parts = []
    for r in p.runs:
        s = _html.escape(r.text or "")
        if not s:
            continue
        st = import_blocs._run_style(r, base)
        parts.append(f'<span style="{st}">{s}</span>' if st else s)
    return "".join(parts) or _html.escape((p.text or "").strip())


def _para_html(p, base, tag: str = "p") -> str:
    align = import_blocs._align_css(getattr(p, "alignment", None))
    style = f' style="text-align:{align}"' if align else ""
    return f"<{tag}{style}>{_runs_inner(p, base)}</{tag}>"


def _table_html(table) -> str:
    rows = []
    for row in table.rows:
        cells = "".join(
            f'<td style="border:1px solid #CBD5E1;padding:4px 6px;">{_html.escape(c.text or "")}</td>'
            for c in row.cells
        )
        rows.append(f"<tr>{cells}</tr>")
    return f'<table style="border-collapse:collapse;width:100%;margin:8px 0;">{"".join(rows)}</table>'


def _docx_tree(data: bytes, filename: str) -> dict:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(data))
    try:
        normal_font = d.styles["Normal"].font
    except Exception:
        normal_font = None

    titre = (d.core_properties.title or "").strip() or os.path.splitext(os.path.basename(filename))[0]

    # Première passe : niveaux de titres réellement présents.
    levels = []
    for p in d.paragraphs:
        txt = (p.text or "").strip()
        if not txt:
            continue
        style = p.style.name if p.style else ""
        if style.lower().startswith("title"):
            continue
        lvl = _docx_heading(p, normal_font)
        if lvl:
            levels.append(lvl)

    distinct = sorted(set(levels))
    if not distinct:
        module_lvl = sequence_lvl = bloc_lvl = None
    elif len(distinct) == 1:
        module_lvl, sequence_lvl, bloc_lvl = None, distinct[0], None
    elif len(distinct) == 2:
        module_lvl, sequence_lvl, bloc_lvl = distinct[0], distinct[1], None
    else:
        module_lvl, sequence_lvl, bloc_lvl = distinct[0], distinct[1], distinct[2]

    builder = _Builder(titre, skip_preamble=bool(distinct))

    for child in d.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]

        if tag == "p":
            p = Paragraph(child, d)
            txt = (p.text or "").strip()
            images = import_blocs._docx_images(p, d)
            if not txt:
                if images:
                    builder.add_content(import_blocs._images_html(images), "")
                continue
            style = p.style.name if p.style else ""

            if style.lower().startswith("title"):
                if not builder.modules and _similar(builder.titre, titre):
                    builder.titre = txt
                continue

            lvl = _docx_heading(p, normal_font)
            kind = _kind_of(txt, is_heading=bool(lvl))
            base = _base_font(p, normal_font)

            structural = False
            if builder.cur_quiz is None:
                if kind in ("module", "sequence", "bloc", "quiz"):
                    structural = True
                elif lvl:
                    if module_lvl is not None and lvl == module_lvl:
                        kind, structural = "module", True
                    elif sequence_lvl is not None and lvl == sequence_lvl:
                        kind, structural = "sequence", True
                    elif bloc_lvl is not None and lvl >= bloc_lvl:
                        kind, structural = "bloc", True
            else:
                # Dans un quiz, seuls un nouveau module/séquence/quiz sortent du quiz.
                if kind in ("module", "sequence", "quiz"):
                    structural = True
                elif lvl and module_lvl is not None and lvl == module_lvl:
                    kind, structural = "module", True
                elif lvl and sequence_lvl is not None and lvl == sequence_lvl:
                    kind, structural = "sequence", True

            if structural:
                # Le titre du document en tête n'est pas un module.
                if builder._first_heading and _similar(txt, titre) and kind in ("module", "sequence"):
                    builder._first_heading = False
                    continue
                builder._first_heading = False
                builder.heading(kind, txt)
                continue

            html = _para_html(p, base, tag=f"h{lvl}") if lvl else _para_html(p, base)
            if images:
                html += import_blocs._images_html(images)
            builder.add_content(html, txt)

        elif tag == "tbl":
            try:
                builder.add_content(_table_html(Table(child, d)), "")
            except Exception:
                continue

    return builder.finish()


# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_tree(data: bytes, filename: str) -> dict:
    info = pdf_style.pdf_lines(data)
    pages = info.get("pages") or []
    titre = (info.get("titre") or "").strip() or os.path.splitext(os.path.basename(filename))[0]

    # En-têtes / pieds de page récurrents.
    total_pages = max(1, len(pages))
    freq = Counter()
    for p in pages:
        for t in {l["text"].strip() for l in p["lines"] if len(l["text"].strip()) <= 120}:
            freq[t] += 1
    repeated = {
        t for t, n in freq.items()
        if n >= max(3, int(total_pages * 0.6)) and not _kind_of(t) and not re.fullmatch(r"[\d\s\-–—/]+", t)
    }

    lines = []
    for p in pages:
        for l in p["lines"]:
            t = l["text"].strip()
            if not t or t in repeated:
                continue
            if re.fullmatch(r"[\d\s\-–—/]+", t):  # numéro de page
                continue
            lines.append({**l, "page": p["page"]})

    if not lines:
        # PDF probablement scanné : tentative d'OCR (si tesseract est installé).
        try:
            from courses import ocr
            if ocr.disponible():
                page_texts = [t for t in ocr.ocr_pdf_pages(data) if (t or "").strip()]
                if page_texts:
                    builder = _Builder(titre)
                    builder.warnings.append(
                        "PDF scanné : texte extrait par OCR (mise en forme approximative)."
                    )
                    builder.heading("module", titre)
                    builder.heading("sequence", "Contenu OCR")
                    for i, text in enumerate(page_texts, start=1):
                        builder.heading("bloc", f"Page {i}")
                        builder.add_content(import_blocs._text_to_html(text), "")
                    return builder.finish()
        except Exception:
            logger.exception("OCR du PDF échoué (%s)", filename)
        builder = _Builder(titre)
        builder.warnings.append(
            "Aucun texte détecté (PDF scanné ou vide ?). "
            "Installez tesseract-ocr et poppler-utils pour activer l'OCR."
        )
        return builder.finish()

    sizes = Counter(round(l["size"], 1) for l in lines)
    body = sizes.most_common(1)[0][0]

    # Tailles de titres : nettement plus grandes que le corps du texte ET
    # récurrentes (>= 2 pages ou >= 3 occurrences) pour écarter la couverture.
    size_pages = {}
    for l in lines:
        size_pages.setdefault(round(l["size"], 1), set()).add(l["page"])
    cands = [
        s for s in size_pages
        if s >= body * 1.15 and (len(size_pages[s]) >= 2 or sizes[s] >= 3)
    ]
    if not cands:
        cands = [s for s in size_pages if s >= body * 1.15]
    big = sorted(cands, reverse=True)[:3]
    level_of = {s: i + 1 for i, s in enumerate(big)}
    builder = _Builder(titre, skip_preamble=bool(big))

    if len(big) == 0:
        module_lvl = sequence_lvl = bloc_lvl = None
    elif len(big) == 1:
        module_lvl, sequence_lvl, bloc_lvl = None, 1, None
    elif len(big) == 2:
        module_lvl, sequence_lvl, bloc_lvl = 1, 2, None
    else:
        module_lvl, sequence_lvl, bloc_lvl = 1, 2, 3

    def same_style(a, b) -> bool:
        return (
            abs(a["size"] - b["size"]) < 0.25
            and a["font"] == b["font"]
            and a["align"] == b["align"]
            and a["color"] == b["color"]
        )

    cur = None

    def flush():
        nonlocal cur
        if cur and cur["inners"]:
            style = f'font-family:{pdf_style._family(cur["font"])};font-size:{cur["size"]}pt;'
            if cur["color"]:
                style += f"color:{cur['color']};"
            if cur["align"]:
                style += f"text-align:{cur['align']};"
            html = f'<p style="{style}">' + "<br>".join(cur["inners"]) + "</p>"
            builder.add_content(html, cur["text"])
        cur = None

    for l in lines:
        text = l["text"].strip()
        size = round(l["size"], 1)
        is_heading = (
            size in level_of
            and len(text) <= 140
            and not text.endswith((".", ";"))
        )
        kind = _kind_of(text, is_heading=is_heading)

        structural_kind = None
        if builder.cur_quiz is None:
            if kind in ("module", "sequence", "bloc", "quiz"):
                structural_kind = kind
            elif is_heading:
                lvl = level_of[size]
                if module_lvl is not None and lvl == module_lvl:
                    structural_kind = "module"
                elif sequence_lvl is not None and lvl == sequence_lvl:
                    structural_kind = "sequence"
                elif bloc_lvl is not None and lvl >= bloc_lvl:
                    structural_kind = "bloc"
        else:
            if kind in ("module", "sequence", "quiz"):
                structural_kind = kind
            elif is_heading and module_lvl is not None and level_of.get(size) == module_lvl:
                structural_kind = "module"
            elif is_heading and sequence_lvl is not None and level_of.get(size) == sequence_lvl:
                structural_kind = "sequence"

        if structural_kind:
            flush()
            if builder._first_heading and _similar(text, titre) and structural_kind in ("module", "sequence"):
                builder._first_heading = False
                continue
            builder._first_heading = False
            builder.heading(structural_kind, text)
            continue

        if cur is None:
            cur = {
                "size": size,
                "font": l["font"],
                "color": l["color"],
                "align": l["align"],
                "inners": [l["inner"]],
                "text": text,
                "last_bottom": l["bottom"],
                "page": l["page"],
            }
        else:
            gap = float(l["top"]) - float(cur["last_bottom"])
            if l["page"] == cur["page"] and same_style(cur, l) and gap <= 0.75 * max(size, 6):
                cur["inners"].append(l["inner"])
                cur["text"] += " " + text
                cur["last_bottom"] = l["bottom"]
            else:
                flush()
                cur = {
                    "size": size,
                    "font": l["font"],
                    "color": l["color"],
                    "align": l["align"],
                    "inners": [l["inner"]],
                    "text": text,
                    "last_bottom": l["bottom"],
                    "page": l["page"],
                }

    flush()
    return builder.finish()


# ─────────────────────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED = (".docx", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")


def _image_tree(data: bytes, filename: str) -> dict:
    import os as _os
    titre = _os.path.splitext(_os.path.basename(filename or ""))[0] or "Image importée"
    builder = _Builder(titre)
    try:
        from courses import ocr
        if not ocr.disponible():
            builder.warnings.append(
                "OCR indisponible : installez tesseract-ocr et pytesseract pour importer une image."
            )
            return builder.finish()
        text = ocr.ocr_image(data)
        if not (text or "").strip():
            builder.warnings.append("Aucun texte détecté dans l'image.")
            return builder.finish()
        builder.warnings.append("Image : texte extrait par OCR (mise en forme approximative).")
        builder.heading("module", titre)
        builder.heading("sequence", "Contenu OCR")
        builder.heading("bloc", "Page 1")
        builder.add_content(import_blocs._text_to_html(text), "")
    except Exception:
        logger.exception("OCR de l'image échoué (%s)", filename)
        builder.warnings.append("Impossible d'extraire le texte de l'image.")
    return builder.finish()


def extract_course(filename: str, data: bytes) -> dict:
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return _docx_tree(data, filename)
    if name.endswith(".pdf"):
        return _pdf_tree(data, filename)
    if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        return _image_tree(data, filename)
    raise ValueError(
        "Format non pris en charge : utilisez un fichier Word (.docx), PDF ou image (.png, .jpg, .tif)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Création en base
# ─────────────────────────────────────────────────────────────────────────────

def create_course_from_tree(user, meta: dict, tree: dict):
    """Crée le cours et toute son arborescence dans une transaction."""
    from django.db import transaction

    from courses.models import BlocContenu, Cours, Module, Sequence
    from courses.serializers import CoursSerializer
    from evaluations.models import Question, Quiz, Reponse

    with transaction.atomic():
        serializer = CoursSerializer(data=meta)
        serializer.is_valid(raise_exception=True)
        cours = serializer.save()

        for m in tree.get("modules", []):
            module = Module.objects.create(
                cours=cours,
                titre=(m.get("titre") or "Module")[:255],
                description=m.get("description") or "",
                ordre=m.get("ordre") or 0,
            )
            for s in m.get("sequences", []):
                sequence = Sequence.objects.create(
                    module=module,
                    titre=(s.get("titre") or "Séquence")[:255],
                    description=s.get("description") or "",
                    ordre=s.get("ordre") or 0,
                )
                for b in s.get("blocs", []):
                    BlocContenu.objects.create(
                        sequence=sequence,
                        titre=(b.get("titre") or "Contenu")[:255],
                        type_bloc=b.get("type_bloc") or "html",
                        ordre=b.get("ordre") or 0,
                        contenu_html=b.get("contenu") or "",
                        est_obligatoire=bool(b.get("est_obligatoire", True)),
                        est_visible=bool(b.get("est_visible", True)),
                    )
                for q in s.get("quizzes", []):
                    quiz = Quiz.objects.create(
                        sequence=sequence,
                        titre=(q.get("titre") or "Quiz")[:255],
                        description=q.get("description") or "",
                    )
                    for i, item in enumerate(q.get("questions", []), start=1):
                        tq = item.get("type_question")
                        if tq not in ("choix_unique", "choix_multiple"):
                            tq = "choix_unique"
                        question = Question.objects.create(
                            quiz=quiz,
                            enonce_texte=item.get("enonce_texte") or "",
                            type_question=tq,
                            points=float(item.get("points") or 1.0),
                            ordre=i,
                            indication_reponse=item.get("indication_reponse") or "",
                        )
                        for j, r in enumerate(item.get("reponses", []), start=1):
                            Reponse.objects.create(
                                question=question,
                                texte=r.get("texte") or "",
                                est_correcte=bool(r.get("est_correcte")),
                                ordre=j,
                            )
        return cours
