"""Publication cours → module → séquence → bloc.

Vérifie :
- qu'un contenu publié d'un cours futur reste inaccessible avant la date du cours ;
- que les nouveaux contenus d'un cours futur naissent « programmés » à sa date ;
- que le changement de date du cours décale les contenus encore programmés
  à l'ancienne date, sans écraser un override explicite.
"""
from datetime import datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import (
    AnneeScolaire, Classe, Groupe, Institution, Matiere, Pays,
)
from courses.models import (
    BlocContenu, Cours, InscriptionCours, Module, Sequence,
)
from courses.publication import (
    appliquer_date_cours, filter_disponibles, module_disponible,
)
from courses.serializers import ModuleSerializer
from users.models import Apprenant, Formateur, UserRole


def _dt(day):
    return timezone.make_aware(datetime.combine(day, time.min))


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pays = Pays.objects.create(nom='Sénégal', code='SN')
        cls.inst = Institution.objects.create(nom="Sup'Info", pays=cls.pays)
        cls.annee = AnneeScolaire.objects.create(
            institution=cls.inst, annee_format_classique='2025-2026', est_active=True,
        )
        cls.classe = Classe.objects.create(
            nom='L3 Info', institution=cls.inst, annee_scolaire=cls.annee,
        )
        cls.groupe = Groupe.objects.create(
            nom='G1', institution=cls.inst, annee_scolaire=cls.annee,
            classe=cls.classe,
        )
        cls.matiere = Matiere.objects.create(institution=cls.inst, nom='Développement')
        cls.formateur = Formateur.objects.create(
            email='formateur.pub@example.com', nom='Sow', prenom='Ibrahima',
            institution=cls.inst, is_active=True,
        )
        cls.formateur.institutions.add(cls.inst)

        cls.aujourdhui = timezone.localdate()
        cls.date1 = cls.aujourdhui + timedelta(days=10)
        cls.date2 = cls.aujourdhui + timedelta(days=20)
        cls.date3 = cls.aujourdhui + timedelta(days=30)

        cls.cours = Cours.objects.create(
            titre='Cours futur', groupe=cls.groupe, enseignant=cls.formateur,
            matiere=cls.matiere, institution=cls.inst, annee_scolaire=cls.annee,
            date_debut=cls.date1,
        )
        cls.module = Module.objects.create(
            titre='Module publié', cours=cls.cours, ordre=1,
            institution=cls.inst, annee_scolaire=cls.annee,
            etat_publication='publie',
        )
        cls.sequence = Sequence.objects.create(
            titre='Séquence', module=cls.module, ordre=1,
            institution=cls.inst, annee_scolaire=cls.annee,
            etat_publication='publie',
        )
        cls.bloc = BlocContenu.objects.create(
            sequence=cls.sequence, titre='Bloc', type_bloc='texte', ordre=1,
            etat_publication='publie',
        )
        role_apprenant = UserRole.objects.get_or_create(name='Apprenant')[0]
        cls.apprenant = Apprenant.objects.create(
            email='apprenant.pub@example.com', nom='Fall', prenom='Awa',
            role=role_apprenant,
            institution=cls.inst, groupe=cls.groupe, is_active=True,
        )
        InscriptionCours.objects.create(
            apprenant=cls.apprenant, cours=cls.cours, statut='en_cours',
            institution=cls.inst, annee_scolaire=cls.annee,
        )

    def setUp(self):
        self.client = APIClient()


class CoursFuturInaccessibleTests(_Base):
    def test_module_publie_non_disponible_avant_le_cours(self):
        self.assertFalse(module_disponible(self.module))
        self.assertFalse(
            filter_disponibles(Module.objects.filter(pk=self.module.pk), 'Module').exists()
        )

    def test_api_module_404_avant_le_cours(self):
        self.client.force_authenticate(user=self.apprenant)
        r = self.client.get(f'/api/v1/modules/{self.module.pk}/')
        self.assertEqual(r.status_code, 404, r.content[:400])

        r = self.client.get(f'/api/v1/modules/{self.module.pk}/sequences/')
        self.assertEqual(r.status_code, 403, r.content[:400])

    def test_module_disponible_apres_le_debut_du_cours(self):
        self.cours.date_debut = self.aujourdhui - timedelta(days=1)
        self.cours.save()
        self.assertTrue(module_disponible(self.module))
        self.assertTrue(
            filter_disponibles(Module.objects.filter(pk=self.module.pk), 'Module').exists()
        )

        self.client.force_authenticate(user=self.apprenant)
        r = self.client.get(f'/api/v1/modules/{self.module.pk}/')
        self.assertEqual(r.status_code, 200, r.content[:400])


class DefautPublicationTests(_Base):
    def test_nouveau_module_programme_a_la_date_du_cours(self):
        serializer = ModuleSerializer(data={'cours': self.cours.pk, 'titre': 'Nouveau'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        module = serializer.save()
        self.assertEqual(module.etat_publication, 'programme')
        self.assertIsNotNone(module.date_publication_programmee)
        self.assertEqual(
            module.date_publication_programmee.date(), self.date1,
        )


class CascadeDateCoursTests(_Base):
    def test_changement_date_cours_decale_les_contenus_programmes(self):
        # Module programmé à l'ancienne date du cours.
        m1 = Module.objects.create(
            titre='M1 programmé', cours=self.cours, ordre=2,
            institution=self.inst, annee_scolaire=self.annee,
            etat_publication='programme', date_publication_programmee=_dt(self.date1),
        )
        s1 = Sequence.objects.create(
            titre='S1 programmée', module=m1, ordre=1,
            institution=self.inst, annee_scolaire=self.annee,
            etat_publication='programme', date_publication_programmee=_dt(self.date1),
        )
        b1 = BlocContenu.objects.create(
            sequence=s1, titre='B1 programmé', type_bloc='texte', ordre=1,
            etat_publication='programme', date_publication_programmee=_dt(self.date1),
        )

        # Override explicite : ne doit pas être touché.
        m2 = Module.objects.create(
            titre='M2 override', cours=self.cours, ordre=3,
            institution=self.inst, annee_scolaire=self.annee,
            etat_publication='programme', date_publication_programmee=_dt(self.date3),
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.cours.date_debut = self.date2
            self.cours.save()

        for obj in (m1, s1, b1):
            obj.refresh_from_db()
            self.assertEqual(obj.date_publication_programmee.date(), self.date2)

        m2.refresh_from_db()
        self.assertEqual(m2.date_publication_programmee.date(), self.date3)
