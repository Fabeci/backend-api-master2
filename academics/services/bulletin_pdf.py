# academics/services/bulletin_pdf.py
"""Génération du bulletin PDF (ReportLab)."""
from io import BytesIO


def rendre_bulletin_pdf(apprenant, annee, data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Bulletin {apprenant}")
    st = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>SOMAPRO</b> — Sup'Info", st["Title"]))
    story.append(Paragraph(
        f"Bulletin de {apprenant.prenom} {apprenant.nom} — {annee}", st["Normal"]))
    story.append(Spacer(1, 8))

    for sem in data.get("semestres", []):
        story.append(Paragraph(
            f"<b>{sem['libelle']}</b> — moyenne {sem['moyenne'] or '—'}/20 · "
            f"{sem['credits_acquis']}/{sem['credits_requis']} crédits · "
            f"{'validé' if sem['valide'] else 'non validé'}", st["Heading2"]))
        rows = [["UE", "Crédits", "Coef.", "Moyenne", "État"]]
        for u in sem["ues"]:
            rows.append([f"{u['code']} — {u['libelle']}", str(u["credits"]),
                         str(u["coefficient"]), str(u["moyenne"] or "—"),
                         "Validée" if u["valide"] else "Ajournée"])
            for e in u["ecs"]:
                rows.append([f"    {e['code']}", str(e["credits"]), str(e["coefficient"]),
                             str(e["moyenne"] or "—"), ""])
        t = Table(rows, colWidths=[90 * mm, 20 * mm, 18 * mm, 22 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E71B4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    story.append(Paragraph(
        f"<b>Moyenne annuelle :</b> {data.get('moyenne_annee') or '—'}/20 &nbsp;&nbsp; "
        f"<b>Crédits :</b> {data['credits_acquis']}/{data['credits_annee']} &nbsp;&nbsp; "
        f"<b>Mention :</b> {data.get('mention') or '—'} &nbsp;&nbsp; "
        f"<b>Décision :</b> {'Admis' if data['valide_annee'] else 'Ajourné'}", st["Normal"]))

    doc.build(story)
    return buffer.getvalue()
