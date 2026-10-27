# core/tests_metier.py
# ============================================================================
# Tests unitaires des règles métier critiques (publication, progression,
# LMD, évaluations, périmètre parent). Complète les tests d'intégration.
# Lancer : python manage.py test core.tests_metier -v2
# ============================================================================
from datetime import timedelta

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
from courses.publication import bloc_disponible, element_publie, filter_disponibles
from courses.services.progression import recompute_all_from_bloc
from evaluations.models import Evaluation, PassageEvaluation
from locations.models import Pays
from users.access_control import accessible_apprenants, user_can_access_apprenant
from users.models import Apprenant, Formateur, Parent, UserRole


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
