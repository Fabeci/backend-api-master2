# core/tests_metier.py
# ============================================================================
# Tests unitaires des règles métier critiques (publication, progression,
# LMD, évaluations, périmètre parent). Complète les tests d'intégration.
# Lancer : python manage.py test core.tests_metier -v2
# ============================================================================
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from academics.models import (
    AnneeScolaire, Classe, Groupe, Institution, Matiere, Semestre, UE,
)
from academics.services.lmd import (
    meilleure_note, mention, moyenne_semestre, moyenne_ue,
)
from courses.models import (
    BlocContenu, BlocProgress, Cours, InscriptionCours, Module, Sequence,
)
from courses.parcours_engine import bloc_est_valide, is_bloc_unlocked_for, validate_block
from courses.publication import (
    appliquer_etat_module, bloc_disponible, element_publie,
    filter_disponibles, peut_publier_bloc, peut_publier_sequence,
)
from courses.services.progression import recompute_all_from_bloc
from evaluations.models import Evaluation, PassageEvaluation, Question, Quiz, Reponse
from locations.models import Pays
from users.access_control import accessible_apprenants, user_can_access_apprenant
from core.rbac import has_permission
from analytics.models import BlocAnalyticsSummary, LearnerProfile
from users.models import Apprenant, Formateur, Parent, RolePermissionOverride, User, UserRole


class BaseMetierTests(TestCase):
    def setUp(self):
        self.pays = Pays.objects.create(nom="Sénégal", code="SN")
        self.inst = Institution.objects.create(nom="Sup'Info", pays=self.pays)
        self.annee = AnneeScolaire.objects.create(
            institution=self.inst, annee_format_classique="2025-2026", est_active=True)
        self.roles = {n: UserRole.objects.get_or_create(name=n)[0]
                      for n in ["Formateur", "Apprenant", "Parent"]}

        self.classe = Classe.objects.create(
            nom="L3 Info", institution=self.inst, annee_scolaire=self.annee)
        self.groupe = Groupe.objects.create(
            nom="G1", institution=self.inst, annee_scolaire=self.annee,
            classe=self.classe)
        self.matiere = Matiere.objects.create(institution=self.inst, nom="Algorithmique")

        self.formateur = Formateur.objects.create(
            email="form@metier.t", nom="F", prenom="T",
            role=self.roles["Formateur"], institution=self.inst, is_active=True)
        self.formateur.institutions.add(self.inst)

        self.apprenant = Apprenant.objects.create(
            email="appr@metier.t", nom="A", prenom="T",
            role=self.roles["Apprenant"], institution=self.inst, is_active=True,
            groupe=self.groupe)

        self.cours = Cours.objects.create(
            titre="Algorithmique", institution=self.inst, annee_scolaire=self.annee,
            matiere=self.matiere, groupe=self.groupe, enseignant=self.formateur)
        InscriptionCours.objects.create(
            apprenant=self.apprenant, cours=self.cours, statut="inscrit",
            institution=self.inst, annee_scolaire=self.annee)

        self.module = Module.objects.create(titre="Structures", cours=self.cours)
        self.sequence = Sequence.objects.create(titre="Piles", module=self.module)


# ============================================================================
# 1. PUBLICATION PROGRESSIVE
# ============================================================================
class PublicationTests(BaseMetierTests):
    def _bloc(self, titre="Bloc", **kwargs):
        params = dict(sequence=self.sequence, titre=titre, type_bloc="texte",
                      contenu_texte="Contenu.", etat_publication="publie")
        params.update(kwargs)
        return BlocContenu.objects.create(**params)

    def test_element_publie_selon_etat(self):
        for etat in ("brouillon", "depublie"):
            self.assertFalse(element_publie(self._bloc(f"Bloc {etat}", etat_publication=etat)))

        publie = self._bloc("Publié")
        self.assertTrue(element_publie(publie))

    def test_programme_selon_la_date(self):
        futur = self._bloc(
            "Futur", etat_publication="programme",
            date_publication_programmee=timezone.now() + timedelta(days=2))
        self.assertFalse(element_publie(futur))

        passe = self._bloc(
            "Passé", etat_publication="programme",
            date_publication_programmee=timezone.now() - timedelta(days=2))
        self.assertTrue(element_publie(passe))

    def test_bloc_disponible_cascade(self):
        bloc = self._bloc("Cascade")
        self.assertTrue(bloc_disponible(bloc))

        self.sequence.etat_publication = "brouillon"
        self.sequence.save(update_fields=["etat_publication"])
        self.assertFalse(bloc_disponible(bloc))

    def test_bloc_masque_non_disponible(self):
        bloc = self._bloc("Masqué", est_visible=False)
        self.assertFalse(bloc_disponible(bloc))

    def test_filter_disponibles(self):
        _ = self._bloc("Visible")
        self._bloc("Brouillon", etat_publication="brouillon")

        qs = filter_disponibles(
            BlocContenu.objects.filter(sequence=self.sequence), "BlocContenu")
        titres = list(qs.values_list("titre", flat=True))
        self.assertIn("Visible", titres)
        self.assertNotIn("Brouillon", titres)


# ============================================================================
# 2. PROGRESSION / DÉBLOCAGE
# ============================================================================
class ProgressionTests(BaseMetierTests):
    def setUp(self):
        super().setUp()
        self.b1 = BlocContenu.objects.create(
            sequence=self.sequence, titre="B1", type_bloc="texte",
            contenu_texte="1", est_obligatoire=True)
        self.b2 = BlocContenu.objects.create(
            sequence=self.sequence, titre="B2", type_bloc="texte",
            contenu_texte="2", est_obligatoire=True)
        self.b3 = BlocContenu.objects.create(
            sequence=self.sequence, titre="B3", type_bloc="texte",
            contenu_texte="3", est_obligatoire=False)

    def _terminer(self, bloc):
        BlocProgress.objects.update_or_create(
            apprenant=self.apprenant, bloc=bloc,
            defaults={"est_termine": True, "etat": "termine"},
        )

    def test_partiel_ne_termine_pas_la_sequence(self):
        from courses.models import SequenceProgress
        self._terminer(self.b1)
        recompute_all_from_bloc(self.apprenant, self.b1)
        self.assertFalse(SequenceProgress.objects.get(
            apprenant=self.apprenant, sequence=self.sequence).est_termine)

    def test_tous_les_blocs_obligatoires_termine_sequence_module_cours(self):
        self._terminer(self.b1)
        self._terminer(self.b2)
        recompute_all_from_bloc(self.apprenant, self.b2)

        from courses.models import CoursProgress, ModuleProgress, SequenceProgress
        self.assertTrue(SequenceProgress.objects.get(
            apprenant=self.apprenant, sequence=self.sequence).est_termine)
        self.assertTrue(ModuleProgress.objects.get(
            apprenant=self.apprenant, module=self.module).est_termine)
        self.assertTrue(CoursProgress.objects.get(
            apprenant=self.apprenant, cours=self.cours).est_termine)

    def test_bloc_facultatif_ne_bloque_pas(self):
        from courses.models import SequenceProgress
        self._terminer(self.b1)
        self._terminer(self.b2)
        # b3 (facultatif) n'est pas terminé : la séquence doit quand même être terminée.
        recompute_all_from_bloc(self.apprenant, self.b2)
        self.assertTrue(SequenceProgress.objects.get(
            apprenant=self.apprenant, sequence=self.sequence).est_termine)


# ============================================================================
# 3. CALCULS LMD
# ============================================================================
class LMDTests(BaseMetierTests):
    def setUp(self):
        super().setUp()
        self.semestre = Semestre.objects.create(
            classe=self.classe, annee_scolaire=self.annee, numero=5,
            institution=self.inst)
        self.ue = UE.objects.create(
            semestre=self.semestre, code="DEV", libelle="Développement",
            credits=6, coefficient=1, institution=self.inst)

    def _ec_avec_note(self, nom, note, coefficient=1.0, session="normale"):
        ec = Matiere.objects.create(
            institution=self.inst, nom=nom, ue=self.ue,
            credits=3, coefficient=coefficient, est_actif=True)
        cours = Cours.objects.create(
            titre=f"Cours {nom}", institution=self.inst, annee_scolaire=self.annee,
            matiere=ec, groupe=self.groupe, enseignant=self.formateur)
        InscriptionCours.objects.create(
            apprenant=self.apprenant, cours=cours, statut="inscrit",
            institution=self.inst, annee_scolaire=self.annee)
        evaluation = Evaluation.objects.create(
            cours=cours, enseignant=self.formateur, titre=f"Éval {nom}",
            type_evaluation="structuree", bareme=20,
            date_debut=timezone.now() - timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=1),
            est_publiee=True, coefficient=1, categorie="examen",
        )
        PassageEvaluation.objects.create(
            apprenant=self.apprenant, evaluation=evaluation, statut="corrige",
            session=session, numero_tentative=1, note=note,
        )
        return ec, evaluation

    def test_mention_seuils(self):
        self.assertIsNone(mention(None))
        self.assertEqual(mention(9.99), "Ajourné")
        self.assertEqual(mention(10), "Passable")
        self.assertEqual(mention(12), "Assez bien")
        self.assertEqual(mention(14), "Bien")
        self.assertEqual(mention(16), "Très bien")
        self.assertEqual(mention(18), "Excellent")

    def test_ue_validee_seulement_au_seuil(self):
        self._ec_avec_note("EC1", 12)
        resultat = moyenne_ue(self.apprenant, self.ue)
        self.assertEqual(resultat["moyenne"], 12.0)
        self.assertTrue(resultat["valide"])
        self.assertEqual(resultat["credits_acquis"], 6)

        # Deuxième EC à 6 → moyenne pondérée 9 → UE non validée.
        self._ec_avec_note("EC2", 6)
        resultat = moyenne_ue(self.apprenant, self.ue)
        self.assertEqual(resultat["moyenne"], 9.0)
        self.assertFalse(resultat["valide"])
        self.assertEqual(resultat["credits_acquis"], 0)

    def test_semestre_strict(self):
        self._ec_avec_note("EC1", 12)
        self.assertTrue(moyenne_semestre(self.apprenant, self.semestre)["valide"])

        # Deuxième UE non validée → semestre invalidé (règle stricte).
        ue2 = UE.objects.create(
            semestre=self.semestre, code="MATH", libelle="Maths",
            credits=6, coefficient=1, institution=self.inst)
        ec2 = Matiere.objects.create(
            institution=self.inst, nom="Analyse", ue=ue2, credits=3,
            coefficient=1, est_actif=True)
        cours2 = Cours.objects.create(
            titre="Analyse", institution=self.inst, annee_scolaire=self.annee,
            matiere=ec2, groupe=self.groupe, enseignant=self.formateur)
        InscriptionCours.objects.create(
            apprenant=self.apprenant, cours=cours2, statut="inscrit",
            institution=self.inst, annee_scolaire=self.annee)
        ev2 = Evaluation.objects.create(
            cours=cours2, enseignant=self.formateur, titre="Partiel",
            type_evaluation="structuree", bareme=20,
            date_debut=timezone.now() - timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=1),
            est_publiee=True, coefficient=1, categorie="examen")
        PassageEvaluation.objects.create(
            apprenant=self.apprenant, evaluation=ev2, statut="corrige",
            session="normale", numero_tentative=1, note=5)

        resultat = moyenne_semestre(self.apprenant, self.semestre)
        self.assertFalse(resultat["valide"])
        self.assertEqual(resultat["credits_acquis"], 6)  # seule la 1ʳᵉ UE validée

    def test_rattrapage_meilleure_note(self):
        _, evaluation = self._ec_avec_note("EC1", 8, session="normale")
        PassageEvaluation.objects.create(
            apprenant=self.apprenant, evaluation=evaluation, statut="corrige",
            session="rattrapage", numero_tentative=2, note=14,
        )
        self.assertEqual(meilleure_note(self.apprenant, evaluation), 14.0)


# ============================================================================
# 4. ÉVALUATIONS : VALIDATIONS ET RÉSULTATS
# ============================================================================
class EvaluationMetierTests(BaseMetierTests):
    def _evaluation(self, **kwargs):
        params = dict(
            cours=self.cours, enseignant=self.formateur, titre="Examen",
            type_evaluation="structuree", bareme=20,
            date_debut=timezone.now() - timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=1),
            est_publiee=True, coefficient=1, categorie="examen")
        params.update(kwargs)
        return Evaluation.objects.create(**params)

    def test_simple_sans_sujet_invalide(self):
        evaluation = Evaluation(
            cours=self.cours, enseignant=self.formateur, titre="Simple",
            type_evaluation="simple", bareme=20, coefficient=1,
            categorie="examen")
        with self.assertRaises(ValidationError):
            evaluation.full_clean()

    def test_accessibilite_selon_publication_et_dates(self):
        non_publiee = self._evaluation(est_publiee=False)
        self.assertFalse(non_publiee.est_accessible())

        future = self._evaluation(
            date_debut=timezone.now() + timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=2))
        self.assertFalse(future.est_accessible())

        ouverte = self._evaluation()
        self.assertTrue(ouverte.est_accessible())

    def test_pourcentage_et_note_invalide(self):
        evaluation = self._evaluation(bareme=20)
        passage = PassageEvaluation(
            apprenant=self.apprenant, evaluation=evaluation, statut="corrige",
            session="normale", numero_tentative=1, note=15)
        self.assertEqual(passage.pourcentage(), 75.0)

        passage.note = 25
        with self.assertRaises(ValidationError):
            passage.full_clean()

        passage.note = -1
        with self.assertRaises(ValidationError):
            passage.full_clean()


# ============================================================================
# 5. PÉRIMÈTRE PARENT / APPRENANT
# ============================================================================
class PerimetreParentTests(BaseMetierTests):
    def setUp(self):
        super().setUp()
        self.parent = Parent.objects.create(
            email="parent@metier.t", nom="P", prenom="T",
            role=self.roles["Parent"], institution=self.inst, is_active=True)
        self.apprenant.tuteur = self.parent
        self.apprenant.save(update_fields=["tuteur"])

        self.autre = Apprenant.objects.create(
            email="autre@metier.t", nom="B", prenom="T",
            role=self.roles["Apprenant"], institution=self.inst, is_active=True)

    def test_parent_ne_voit_que_ses_enfants(self):
        autorises = accessible_apprenants(self.parent)
        ids = set(autorises.values_list("id", flat=True))
        self.assertIn(self.apprenant.id, ids)
        self.assertNotIn(self.autre.id, ids)

        self.assertTrue(user_can_access_apprenant(self.parent, self.apprenant))
        self.assertFalse(user_can_access_apprenant(self.parent, self.autre))

    def test_apprenant_ne_voit_que_lui_meme(self):
        autorises = accessible_apprenants(self.apprenant)
        ids = set(autorises.values_list("id", flat=True))
        self.assertEqual(ids, {self.apprenant.id})


# ============================================================================
# 6. ÉTATS D'UN COURS (planifié / en cours / terminé / annulé)
# ============================================================================
class CoursStatutTests(BaseMetierTests):
    def _base(self):
        return dict(institution=self.inst, annee_scolaire=self.annee,
                    matiere=self.matiere, groupe=self.groupe, enseignant=self.formateur)

    def test_statut_selon_les_dates(self):
        today = timezone.localdate()
        futur = Cours(titre="F", date_debut=today + timedelta(days=2),
                      date_fin=today + timedelta(days=10), **self._base())
        self.assertEqual(futur.statut_calcule, "planifie")

        en_cours = Cours(titre="E", date_debut=today - timedelta(days=1),
                         date_fin=today + timedelta(days=1), **self._base())
        self.assertEqual(en_cours.statut_calcule, "en_cours")

        termine = Cours(titre="T", date_debut=today - timedelta(days=10),
                        date_fin=today - timedelta(days=1), **self._base())
        self.assertEqual(termine.statut_calcule, "termine")

    def test_statut_sans_dates(self):
        self.assertEqual(self.cours.statut_calcule, "planifie")

    def test_statut_force_respecte(self):
        c = Cours(titre="Annulé", statut="annule", statut_force=True, **self._base())
        self.assertEqual(c.statut_calcule, "annule")

    def test_cours_annule_force_le_statut_a_la_sauvegarde(self):
        matiere = Matiere.objects.create(institution=self.inst, nom="Annulation")
        c = Cours.objects.create(
            titre="Annulé", institution=self.inst, annee_scolaire=self.annee,
            matiere=matiere, groupe=self.groupe, enseignant=self.formateur,
            statut="annule", date_debut=timezone.localdate() - timedelta(days=1),
            date_fin=timezone.localdate() + timedelta(days=1))
        self.assertTrue(c.statut_force)
        self.assertEqual(c.statut, "annule")


# ============================================================================
# 7. TRANSITIONS DE PUBLICATION (module → séquences → blocs)
# ============================================================================
class PublicationTransitionTests(BaseMetierTests):
    def setUp(self):
        super().setUp()
        self.bloc = BlocContenu.objects.create(
            sequence=self.sequence, titre="B", type_bloc="texte",
            contenu_texte="x", etat_publication="brouillon")
        self.sequence.etat_publication = "brouillon"
        self.sequence.save(update_fields=["etat_publication"])
        self.module.etat_publication = "brouillon"
        self.module.save(update_fields=["etat_publication"])

    def test_module_publie_aligne_sequences_et_blocs(self):
        self.module.etat_publication = "publie"
        self.module.save(update_fields=["etat_publication"])
        appliquer_etat_module(self.module)

        self.sequence.refresh_from_db()
        self.bloc.refresh_from_db()
        self.assertEqual(self.sequence.etat_publication, "publie")
        self.assertEqual(self.bloc.etat_publication, "publie")
        self.assertIsNotNone(self.bloc.date_publication_effective)

    def test_module_programme_propage_la_date(self):
        date = timezone.now() + timedelta(days=2)
        self.module.etat_publication = "programme"
        self.module.date_publication_programmee = date
        self.module.save(update_fields=["etat_publication", "date_publication_programmee"])
        appliquer_etat_module(self.module)

        self.sequence.refresh_from_db()
        self.bloc.refresh_from_db()
        self.assertEqual(self.sequence.etat_publication, "programme")
        self.assertEqual(self.bloc.date_publication_programmee, date)

    def test_module_depublie(self):
        self.module.etat_publication = "depublie"
        self.module.save(update_fields=["etat_publication"])
        appliquer_etat_module(self.module)
        self.bloc.refresh_from_db()
        self.assertEqual(self.bloc.etat_publication, "depublie")

    def test_peut_publier_regles(self):
        self.assertFalse(peut_publier_sequence(self.sequence))
        self.module.etat_publication = "publie"
        self.module.save(update_fields=["etat_publication"])
        self.assertTrue(peut_publier_sequence(self.sequence))

        self.assertFalse(peut_publier_bloc(self.bloc))  # séquence encore brouillon
        self.sequence.etat_publication = "publie"
        self.sequence.save(update_fields=["etat_publication"])
        self.assertTrue(peut_publier_bloc(self.bloc))


# ============================================================================
# 8. CONSULTATION, VALIDATION ET DÉBLOCAGE DU BLOC SUIVANT
# ============================================================================
class ConsultationEtDeblocageTests(BaseMetierTests):
    def setUp(self):
        super().setUp()
        self.b1 = BlocContenu.objects.create(
            sequence=self.sequence, titre="B1", type_bloc="texte", contenu_texte="x",
            ordre=1, est_obligatoire=True, duree_estimee_minutes=10)
        self.b2 = BlocContenu.objects.create(
            sequence=self.sequence, titre="B2", type_bloc="texte", contenu_texte="y",
            ordre=2, est_obligatoire=True)

    def test_consultation_temps_seuil(self):
        summ = BlocAnalyticsSummary(apprenant=self.apprenant, bloc=self.b1,
                                    duree_totale_sec=359)
        self.assertFalse(bloc_est_valide(self.b1, None, summ))
        summ.duree_totale_sec = 360
        self.assertTrue(bloc_est_valide(self.b1, None, summ))

    def test_consultation_scroll_seuil(self):
        summ = BlocAnalyticsSummary(apprenant=self.apprenant, bloc=self.b1,
                                    scroll_max_pct=79)
        self.assertFalse(bloc_est_valide(self.b1, None, summ))
        summ.scroll_max_pct = 80
        self.assertTrue(bloc_est_valide(self.b1, None, summ))

    def test_progress_termine_suffit(self):
        prog = BlocProgress(apprenant=self.apprenant, bloc=self.b1, est_termine=True)
        self.assertTrue(bloc_est_valide(self.b1, prog, None))

    def test_premier_bloc_debloque_second_verrouille(self):
        self.assertTrue(is_bloc_unlocked_for(self.apprenant, self.b1)[0])
        unlocked, raison = is_bloc_unlocked_for(self.apprenant, self.b2)
        self.assertFalse(unlocked)
        self.assertTrue(raison)

    def test_validation_du_premier_debloque_le_second(self):
        BlocProgress.objects.create(apprenant=self.apprenant, bloc=self.b1,
                                    est_termine=True)
        res = validate_block(self.apprenant, self.b1)
        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("valide"))
        self.assertTrue(is_bloc_unlocked_for(self.apprenant, self.b2)[0])

    def test_valider_un_bloc_verrouille_refuse(self):
        res = validate_block(self.apprenant, self.b2)
        self.assertFalse(res.get("ok"))
        self.assertTrue(res.get("raison"))


# ============================================================================
# 9. VALIDATION DES QUESTIONS ET RÉPONSES
# ============================================================================
class QuestionValidationTests(BaseMetierTests):
    def setUp(self):
        super().setUp()
        self.evaluation = Evaluation.objects.create(
            cours=self.cours, enseignant=self.formateur, titre="E",
            type_evaluation="structuree", bareme=20,
            date_debut=timezone.now() - timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=1),
            est_publiee=True, coefficient=1, categorie="examen")

    def test_question_sans_parent_invalide(self):
        q = Question(enonce_texte="Q", type_question="choix_unique", points=1)
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_question_avec_quiz_et_evaluation_invalide(self):
        quiz = Quiz.objects.create(titre="Qz", sequence=self.sequence)
        q = Question(enonce_texte="Q", type_question="choix_unique", points=1,
                     quiz=quiz, evaluation=self.evaluation)
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_quiz_refuse_question_textuelle(self):
        quiz = Quiz.objects.create(titre="Qz", sequence=self.sequence)
        q = Question(enonce_texte="Q", type_question="texte_long", points=1, quiz=quiz)
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_question_choix_correction_manuelle_invalide(self):
        q = Question(enonce_texte="Q", type_question="choix_unique", points=1,
                     evaluation=self.evaluation, mode_correction="manuelle")
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_question_textuelle_correction_auto_invalide(self):
        q = Question(enonce_texte="Q", type_question="texte_long", points=1,
                     evaluation=self.evaluation, mode_correction="automatique")
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_save_definit_le_mode_de_correction(self):
        texte = Question(enonce_texte="Q", type_question="texte_long", points=1,
                         evaluation=self.evaluation)
        texte.save()
        self.assertEqual(texte.mode_correction, "manuelle")

        choix = Question(enonce_texte="Q2", type_question="choix_unique", points=1,
                         evaluation=self.evaluation)
        choix.save()
        self.assertEqual(choix.mode_correction, "automatique")

    def test_reponse_sur_question_textuelle_refusee(self):
        q = Question(enonce_texte="Q", type_question="texte_long", points=1,
                     evaluation=self.evaluation)
        q.save()
        r = Reponse(question=q, texte="x", est_correcte=True)
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_deux_bonnes_reponses_choix_unique_refusees(self):
        q = Question(enonce_texte="Q", type_question="choix_unique", points=1,
                     evaluation=self.evaluation)
        q.save()
        Reponse.objects.create(question=q, texte="A", est_correcte=True)
        r2 = Reponse(question=q, texte="B", est_correcte=True)
        with self.assertRaises(ValidationError):
            r2.full_clean()


# ============================================================================
# 10. RBAC UNITAIRE
# ============================================================================
class RBACUnitTests(BaseMetierTests):
    def test_anonyme_refuse(self):
        self.assertFalse(has_permission(AnonymousUser(), "cours", "view"))

    def test_superuser_autorise(self):
        su = User.objects.create(email="su@metier.t", is_superuser=True)
        self.assertTrue(has_permission(su, "admins", "delete"))

    def test_formateur_cree_du_contenu(self):
        self.assertTrue(has_permission(self.formateur, "cours", "create"))
        self.assertTrue(has_permission(self.formateur, "modules", "edit"))

    def test_formateur_pas_admin(self):
        self.assertFalse(has_permission(self.formateur, "admins", "view"))

    def test_apprenant_lecture_seule(self):
        self.assertTrue(has_permission(self.apprenant, "cours", "view"))
        self.assertFalse(has_permission(self.apprenant, "cours", "create"))

    def test_permission_explicite_additive(self):
        self.apprenant.permissions = ["admins.view"]
        self.apprenant.save(update_fields=["permissions"])
        self.assertTrue(has_permission(self.apprenant, "admins", "view"))

    def test_surcharge_db_prioritaire(self):
        RolePermissionOverride.objects.create(
            role="Apprenant", resource="cours", action="create", allowed=True)
        self.assertTrue(has_permission(self.apprenant, "cours", "create"))

    def test_ressource_inconnue_refusee(self):
        self.assertFalse(has_permission(self.formateur, "ressource_inexistante", "view"))


# ============================================================================
# 11. INDICATEURS PÉDAGOGIQUES (profil adaptatif)
# ============================================================================
class IndicateursTests(BaseMetierTests):
    def test_profil_sans_activite(self):
        profil = LearnerProfile.objects.create(apprenant=self.apprenant)
        profil.recalculer()
        self.assertEqual(profil.score_regularite, 0)
        self.assertEqual(profil.score_engagement, 0)
        self.assertIn(profil.type_contenu_prefere or "", ("", "texte"))


# ============================================================================
# 12. SUIVI DES ÉVALUATIONS
# ============================================================================
class EvaluationSuiviTests(BaseMetierTests):
    def _eval(self, fin, publiee=True):
        return Evaluation.objects.create(
            cours=self.cours, enseignant=self.formateur, titre="E",
            type_evaluation="structuree", bareme=20,
            date_debut=timezone.now() - timedelta(days=2),
            date_fin=fin, est_publiee=publiee, coefficient=1, categorie="examen")

    def test_peut_soumettre_selon_date_fin(self):
        fermee = self._eval(timezone.now() - timedelta(hours=1))
        self.assertFalse(fermee.peut_soumettre())

        ouverte = self._eval(timezone.now() + timedelta(hours=1))
        self.assertTrue(ouverte.peut_soumettre())

    def test_pourcentage_bareme_zero(self):
        ev = self._eval(timezone.now() + timedelta(hours=1))
        ev.bareme = 0
        ev.save(update_fields=["bareme"])
        passage = PassageEvaluation(
            apprenant=self.apprenant, evaluation=ev, statut="corrige", note=10)
        self.assertIsNone(passage.pourcentage())
