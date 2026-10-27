# courses/ocr.py
# =============================================================================
# OCR optionnel pour les PDF scannés et les images.
#
# Dépendances système : tesseract-ocr (+ paquet français) et poppler-utils.
# Dépendances Python : pytesseract, pdf2image, Pillow.
#
# L'OCR est utilisé uniquement lorsque l'extraction texte native ne renvoie
# rien. La mise en forme d'origine n'est pas récupérable : le texte est
# regroupé par page et reste éditable dans l'aperçu d'import.
# =============================================================================

import io
import logging

logger = logging.getLogger(__name__)

MAX_PAGES = 80
DPI = 200


def disponible() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


def _lang() -> str | None:
    try:
        import pytesseract
        langs = pytesseract.get_languages(config="")
        if "fra" in langs:
            return "fra"
        if "eng" in langs:
            return "eng"
    except Exception:
        pass
    return None


def ocr_image(data: bytes) -> str:
    """OCR d'une image (PNG, JPEG, TIFF…)."""
    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    lang = _lang()
    return pytesseract.image_to_string(img, lang=lang) if lang else pytesseract.image_to_string(img)


def ocr_pdf_pages(data: bytes, max_pages: int = MAX_PAGES) -> list[str]:
    """OCR d'un PDF page par page. Retourne une liste de textes."""
    from pdf2image import convert_from_bytes
    import pytesseract

    images = convert_from_bytes(data, dpi=DPI, fmt="png", first_page=1, last_page=max_pages)
    lang = _lang()
    texts = []
    for img in images[:max_pages]:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        try:
            texts.append(pytesseract.image_to_string(img, lang=lang) if lang else pytesseract.image_to_string(img))
        except Exception:
            logger.exception("OCR d'une page PDF échouée")
            texts.append("")
    return texts


def ocr_pdf(data: bytes, max_pages: int = MAX_PAGES) -> str:
    return "\n\n".join(ocr_pdf_pages(data, max_pages=max_pages))
