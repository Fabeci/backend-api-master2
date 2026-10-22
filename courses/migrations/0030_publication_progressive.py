from django.db import migrations, models


FIELDS = [
    ("etat_publication", models.CharField(
        choices=[("brouillon", "Brouillon"), ("programme", "Programmé"),
                 ("publie", "Publié"), ("depublie", "Dépublié")],
        default="publie", max_length=20,
        help_text="brouillon / programmé / publié / dépublié (défaut : publié pour compatibilité)",
        verbose_name="État de publication")),
    ("date_publication_programmee", models.DateTimeField(
        blank=True, null=True, verbose_name="Publication programmée le")),
    ("date_publication_effective", models.DateTimeField(
        blank=True, null=True, verbose_name="Publié effectivement le")),
]


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0029_sessioninvite"),
    ]

    operations = []
    for model in ("module", "sequence", "bloccontenu"):
        for name, field in FIELDS:
            operations.append(
                migrations.AddField(model_name=model, name=name, field=field)
            )
