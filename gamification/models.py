# gamification/models.py
from django.db import models
from django.utils import timezone


# ── Constantes ────────────────────────────────────────────────────────────────

LEVEL_THRESHOLDS = {
    1:  0,       2:  200,     3:  600,     4: 1_300,
    5:  2_500,   6:  4_500,   7:  7_500,   8: 12_000,
    9:  18_500,  10: 27_500,  11: 39_500,  12: 55_500,
    13: 75_500,  14: 100_500, 15: 150_500,
}
LEVEL_TITLES = {
    1:'Novice', 2:'Curieux', 3:'Explorateur', 4:'Apprenant',
    5:'Assidu', 6:'Engagé', 7:'Persévérant', 8:'Avancé',
    9:'Confirmé', 10:'Expert', 11:'Maître', 12:'Mentor',
    13:'Érudit', 14:'Champion', 15:'Légende',
}
XP_TABLE = {
    'connexion':       10,  'bloc_complete':   10,
    'sequence_done':   50,  'module_done':    100,
    'cours_done':     500,  'quiz_participe':  20,
    'quiz_reussi':     20,  'quiz_parfait':    50,
    'eval_soumise':    30,  'eval_reussie':    40,
    'eval_mention':    70,  'eval_tres_bien': 100,
    'ressource_dl':     5,  'forum_post':      25,
    'aide_pair':       40,  'streak_7j':      100,
    'streak_30j':     500,  'streak_90j':    2000,
}
DAILY_CAPS = {
    'connexion': 15, 'contenu': 150, 'evaluations': 200, 'collaboration': 100,
}
STREAK_MULTIPLIERS = {
    0:1.00, 7:1.10, 15:1.20, 30:1.35, 60:1.50, 90:1.75,
}
SOURCE_CATEGORY = {
    'connexion':'connexion',
    'bloc_complete':'contenu', 'sequence_done':'contenu',
    'module_done':'contenu',   'cours_done':'contenu',
    'quiz_participe':'evaluations', 'quiz_reussi':'evaluations',
    'quiz_parfait':'evaluations',   'eval_soumise':'evaluations',
    'eval_reussie':'evaluations',   'eval_mention':'evaluations',
    'eval_tres_bien':'evaluations',
    'forum_post':'collaboration',   'aide_pair':'collaboration',
}


# ── Modèles ────────────────────────────────────────────────────────────────────

class UserLevel(models.Model):
    apprenant  = models.OneToOneField(
        'users.Apprenant', on_delete=models.CASCADE, related_name='gamification_level'
    )
    xp_total   = models.PositiveIntegerField(default=0)
    xp_semaine = models.PositiveIntegerField(default=0)
    niveau     = models.PositiveSmallIntegerField(default=1)
    titre      = models.CharField(max_length=64, default='Novice')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Niveau utilisateur'

    def __str__(self):
        return f'{self.apprenant} — Niv.{self.niveau} ({self.xp_total} XP)'

    def recalculate(self) -> bool:
        """Recalcule le niveau. Retourne True si level-up."""
        nouveau = 1
        for lvl in sorted(LEVEL_THRESHOLDS.keys()):
            if self.xp_total >= LEVEL_THRESHOLDS[lvl]:
                nouveau = lvl
        level_up = nouveau > self.niveau
        self.niveau = nouveau
        self.titre  = LEVEL_TITLES[nouveau]
        self.save(update_fields=['niveau', 'titre', 'updated_at'])
        return level_up

    @property
    def xp_pour_prochain_niveau(self) -> int:
        next_lvl = min(self.niveau + 1, 15)
        return LEVEL_THRESHOLDS[next_lvl]

    @property
    def xp_niveau_actuel(self) -> int:
        return LEVEL_THRESHOLDS[self.niveau]

    @property
    def pct_vers_prochain(self) -> int:
        if self.niveau >= 15:
            return 100
        span = self.xp_pour_prochain_niveau - self.xp_niveau_actuel
        done = self.xp_total - self.xp_niveau_actuel
        return min(100, round(done / span * 100)) if span else 100


class XPTransaction(models.Model):
    apprenant      = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='xp_transactions')
    source         = models.CharField(max_length=32)
    xp             = models.IntegerField()
    multiplicateur = models.FloatField(default=1.0)
    description    = models.CharField(max_length=255, blank=True)
    reference_id   = models.PositiveIntegerField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['apprenant', 'created_at'])]

    def __str__(self):
        return f'+{self.xp} XP ({self.source}) — {self.apprenant}'


class Streak(models.Model):
    apprenant             = models.OneToOneField(
        'users.Apprenant', on_delete=models.CASCADE, related_name='gamification_streak'
    )
    streak_actuel         = models.PositiveIntegerField(default=0)
    streak_max            = models.PositiveIntegerField(default=0)
    derniere_activite     = models.DateField(null=True, blank=True)
    protections_dispo     = models.PositiveSmallIntegerField(default=1)
    protections_utilisees = models.PositiveSmallIntegerField(default=0)
    peut_reparer          = models.BooleanField(default=False)
    reparations_ce_mois   = models.PositiveSmallIntegerField(default=0)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Streak apprenant'

    def __str__(self):
        return f'{self.apprenant} — 🔥 {self.streak_actuel}j'

    @property
    def multiplicateur(self) -> float:
        for palier in sorted(STREAK_MULTIPLIERS.keys(), reverse=True):
            if self.streak_actuel >= palier:
                return STREAK_MULTIPLIERS[palier]
        return 1.0


class Badge(models.Model):
    RARETE_CHOICES = [
        ('commun','Commun'), ('peu_commun','Peu commun'),
        ('rare','Rare'), ('tres_rare','Très rare'), ('legendaire','Légendaire'),
    ]
    CATEGORIES = [
        ('engagement','Engagement'), ('performance','Performance'),
        ('regularite','Régularité'), ('perseverance','Persévérance'),
        ('collaboration','Collaboration'), ('special','Spécial'),
    ]
    code        = models.SlugField(unique=True, max_length=64)
    nom         = models.CharField(max_length=128)
    description = models.TextField()
    categorie   = models.CharField(max_length=32, choices=CATEGORIES)
    rarete      = models.CharField(max_length=16, choices=RARETE_CHOICES, default='commun')
    icone       = models.CharField(max_length=64, blank=True)
    couleur     = models.CharField(max_length=16, blank=True, default='#00b69b')
    conditions  = models.JSONField(default=dict)
    xp_bonus    = models.PositiveSmallIntegerField(default=0)
    est_actif   = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Badge'
        ordering     = ['categorie', 'rarete']

    def __str__(self):
        return f'[{self.rarete}] {self.nom}'


class UserBadge(models.Model):
    apprenant   = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='user_badges')
    badge       = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='holders')
    obtained_at = models.DateTimeField(auto_now_add=True)
    est_affiche = models.BooleanField(default=True)

    class Meta:
        unique_together = ('apprenant', 'badge')
        ordering        = ['-obtained_at']

    def __str__(self):
        return f'{self.apprenant} → {self.badge.nom}'


class Mission(models.Model):
    TYPE_CHOICES = [
        ('quotidienne','Quotidienne'), ('hebdomadaire','Hebdomadaire'),
        ('mensuelle','Mensuelle'),     ('speciale','Spéciale'),
    ]
    DIFFICULTE_CHOICES = [
        ('facile','Facile'), ('normale','Normale'),
        ('difficile','Difficile'), ('defi','Défi'),
    ]
    titre            = models.CharField(max_length=200)
    description      = models.TextField()
    type_mission     = models.CharField(max_length=20, choices=TYPE_CHOICES)
    difficulte       = models.CharField(max_length=16, choices=DIFFICULTE_CHOICES, default='normale')
    action           = models.CharField(max_length=64)
    quantite         = models.PositiveSmallIntegerField(default=1)
    xp_recompense    = models.PositiveIntegerField(default=50)
    badge_recompense = models.ForeignKey(Badge, null=True, blank=True, on_delete=models.SET_NULL)
    adaptative       = models.BooleanField(default=False)
    est_active       = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Mission'
        ordering     = ['type_mission', 'difficulte']

    def __str__(self):
        return f'[{self.type_mission}] {self.titre}'


class UserMission(models.Model):
    STATUT_CHOICES = [
        ('active','Active'), ('completee','Complétée'), ('expiree','Expirée'),
    ]
    apprenant    = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='user_missions')
    mission      = models.ForeignKey(Mission, on_delete=models.CASCADE)
    statut       = models.CharField(max_length=16, choices=STATUT_CHOICES, default='active')
    progression  = models.PositiveSmallIntegerField(default=0)
    cible        = models.PositiveSmallIntegerField(default=1)
    assignee_le  = models.DateTimeField(auto_now_add=True)
    expire_le    = models.DateTimeField()
    completee_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-assignee_le']
        indexes  = [models.Index(fields=['apprenant', 'statut'])]

    def __str__(self):
        return f'{self.apprenant} — {self.mission.titre} ({self.statut})'

    @property
    def pct_progression(self) -> int:
        return min(100, round(self.progression / self.cible * 100)) if self.cible else 0

    def avancer(self, delta: int = 1) -> bool:
        if self.statut != 'active':
            return False
        self.progression = min(self.cible, self.progression + delta)
        if self.progression >= self.cible:
            self.statut      = 'completee'
            self.completee_le = timezone.now()
            self.save()
            return True
        self.save(update_fields=['progression'])
        return False
