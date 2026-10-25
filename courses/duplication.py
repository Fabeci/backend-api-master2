# courses/duplication.py
# ============================================================================
# Duplication de contenu pédagogique entre années scolaires.
#
# On recopie la STRUCTURE et le CONTENU (modules → séquences → blocs →
# contenus de séquence → ressources → quiz/questions/réponses) dans un cours
# cible (année postérieure, même formateur).
#
# Ce qui n'est JAMAIS copié : progression, notes, passages, présences,
# sessions, inscriptions, analytics. Les copies repartent en **brouillon**.
# ============================================================================
from django.db import transaction

from .models import Module, Sequence, BlocContenu, SequenceContent, RessourceSequence


@transaction.atomic
def copier_module(module_src: Module, cours_cible) -> Module:
    """Copie un module et TOUT son contenu dans `cours_cible` (en brouillon)."""
    from evaluations.models import Quiz, Question, Reponse

    institution = cours_cible.institution
    annee       = cours_cible.annee_scolaire

    module = Module.objects.create(
        titre=module_src.titre,
        description=module_src.description,
        cours=cours_cible,
        ordre=module_src.ordre,
        duree_estimee=module_src.duree_estimee,
        institution=institution,
        annee_scolaire=annee,
        etat_publication="brouillon",
    )

    seqs_src = Sequence.objects.filter(module=module_src).order_by("ordre", "id")
    for seq_src in seqs_src:
        seq = Sequence.objects.create(
            titre=seq_src.titre,
            description=seq_src.description,
            ordre=seq_src.ordre,
            module=module,
            institution=institution,
            annee_scolaire=annee,
            quiz_obligatoire=seq_src.quiz_obligatoire,
            quiz_seuil=seq_src.quiz_seuil,
            etat_publication="brouillon",
        )

        # Blocs de contenu
        for b in BlocContenu.objects.filter(sequence=seq_src).order_by("ordre", "id"):
            BlocContenu.objects.create(
                sequence=seq,
                titre=b.titre,
                type_bloc=b.type_bloc,
                ordre=b.ordre,
                contenu_texte=b.contenu_texte,
                contenu_html=b.contenu_html,
                contenu_markdown=b.contenu_markdown,
                video_url=b.video_url,
                audio_url=b.audio_url,
                image=b.image,
                fichier=b.fichier,
                lien_externe=b.lien_externe,
                code_source=b.code_source,
                langage_code=b.langage_code,
                objectifs=b.objectifs,
                duree_estimee_minutes=b.duree_estimee_minutes,
                est_obligatoire=b.est_obligatoire,
                est_visible=b.est_visible,
                etat_publication="brouillon",
            )

        # Contenu de séquence
        for c in SequenceContent.objects.filter(sequence=seq_src):
            SequenceContent.objects.create(
                sequence=seq,
                contenu_texte=c.contenu_texte,
                contenu_html=c.contenu_html,
                video_url=c.video_url,
                lien_externe=c.lien_externe,
                objectifs=c.objectifs,
                duree_estimee_minutes=c.duree_estimee_minutes,
                est_publie=False,
            )

        # Ressources
        for r in RessourceSequence.objects.filter(sequence=seq_src).order_by("ordre", "id"):
            RessourceSequence.objects.create(
                sequence=seq,
                titre=r.titre,
                description=r.description,
                fichier=r.fichier,
                type_ressource=r.type_ressource,
                taille_fichier=r.taille_fichier,
                est_telechargeable=r.est_telechargeable,
                ordre=r.ordre,
                ajoute_par=r.ajoute_par,
            )

        # Quiz + questions + réponses
        for quiz_src in Quiz.objects.filter(sequence=seq_src):
            quiz = Quiz.objects.create(
                sequence=seq,
                titre=quiz_src.titre,
                description=quiz_src.description,
            )
            for q in Question.objects.filter(quiz=quiz_src).order_by("ordre", "id"):
                question = Question.objects.create(
                    quiz=quiz,
                    enonce_texte=q.enonce_texte,
                    fichier_enonce=q.fichier_enonce,
                    type_question=q.type_question,
                    mode_correction=q.mode_correction,
                    points=q.points,
                    ordre=q.ordre,
                    indication_reponse=q.indication_reponse,
                )
                for rep in Reponse.objects.filter(question=q).order_by("ordre", "id"):
                    Reponse.objects.create(
                        question=question,
                        texte=rep.texte,
                        est_correcte=rep.est_correcte,
                        ordre=rep.ordre,
                    )

    return module
