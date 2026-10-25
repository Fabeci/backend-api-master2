# -*- coding: utf-8 -*-
"""Seed : vraie formation « Python & Développement Web » (contenus réels) + quiz + recommandations."""
from django.core.files.base import ContentFile
from academics.models import Institution, AnneeScolaire, Groupe, Matiere
from users.models import Formateur, Apprenant
from courses.models import Cours, Module, Sequence, BlocContenu, RessourceSequence, InscriptionCours, Suivi
from evaluations.models import Quiz, Question, Reponse
from analytics.models import AIAnalysisRequest, ContenuGenere, RecommandationPedagogique

INST_ID, ANNEE_ID, GROUPE_ID, FORMATEUR_ID, APPRENANT_ID = 27, 27, 57, 342, 344

inst   = Institution.objects.get(pk=INST_ID)
annee  = AnneeScolaire.objects.get(pk=ANNEE_ID)
groupe = Groupe.objects.get(pk=GROUPE_ID)
form   = Formateur.objects.get(pk=FORMATEUR_ID)
appr   = Apprenant.objects.get(pk=APPRENANT_ID)

# ── PDF minimal VALIDE (offsets xref calculés) ───────────────────────────────
def make_pdf(title, lines):
    def esc(s):
        return (s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)'))
    parts = ["BT /F1 18 Tf 50 800 Td (%s) Tj ET" % esc(title)]
    y = 772
    for ln in lines:
        parts.append("BT /F1 11 Tf 50 %d Td (%s) Tj ET" % (y, esc(ln)))
        y -= 16
    stream = "\n".join(parts).encode('latin-1', 'replace')
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)

# ── Matière + Cours ──────────────────────────────────────────────────────────
matiere, _ = Matiere.objects.get_or_create(
    institution=inst, nom="Python & Développement Web",
    defaults={'description': "Programmation Python appliquée au développement web (Flask)."},
)

cours, created = Cours.objects.get_or_create(
    groupe=groupe, matiere=matiere, enseignant=form, annee_scolaire=annee,
    defaults={
        'titre': "Python & Développement Web — Parcours pratique",
        'institution': inst,
        'volume_horaire': 30,
        'statut': 'en_cours',
    },
)
cours.titre = "Python & Développement Web — Parcours pratique"
cours.volume_horaire = 30
cours.statut = 'en_cours'
cours.institution = inst
cours.annee_scolaire = annee
cours.save()

# Repartir proprement sur CE cours
Module.objects.filter(cours=cours).delete()

def bloc(seq, ordre, titre, type_bloc, **kw):
    b = BlocContenu(sequence=seq, ordre=ordre, titre=titre, type_bloc=type_bloc)
    for k, v in kw.items():
        setattr(b, k, v)
    b.save()
    return b

def quiz(seq, titre, questions):
    q = Quiz.objects.create(sequence=seq, titre=titre, description="Quiz de validation de la séquence.")
    for i, (enonce, choices) in enumerate(questions, start=1):
        question = Question.objects.create(
            quiz=q, enonce_texte=enonce, type_question='choix_unique',
            mode_correction='automatique', points=1.0, ordre=i,
        )
        for j, (txt, ok) in enumerate(choices, start=1):
            Reponse.objects.create(question=question, texte=txt, est_correcte=ok, ordre=j)
    return q

# ═══════════════════════════ MODULE 1 ═══════════════════════════
m1 = Module.objects.create(cours=cours, titre="Module 1 — Les fondamentaux de Python", ordre=1,
                           duree_estimee=240,
                           description="Découvrir la syntaxe, les variables, les conditions et les boucles.")

s11 = Sequence.objects.create(module=m1, titre="Variables, types et opérateurs", ordre=1,
                              description="Comprendre comment stocker et manipuler des données.")

bloc(s11, 1, "Qu'est-ce qu'une variable ?", "texte", duree_estimee_minutes=10, contenu_html="""
<h3>Une variable, un nom pour une valeur</h3>
<p>En Python, une variable est un <strong>nom</strong> qui référence une valeur en mémoire. On l'affecte avec le signe <code>=</code> :</p>
<pre><code>age = 25
prenom = "Awa"
</code></pre>
<p>Python est <em>typé dynamiquement</em> : le type est déduit automatiquement de la valeur.</p>
<ul>
  <li><code>int</code> : nombres entiers — <code>42</code></li>
  <li><code>float</code> : nombres décimaux — <code>3.14</code></li>
  <li><code>str</code> : chaînes de caractères — <code>"bonjour"</code></li>
  <li><code>bool</code> : booléens — <code>True</code> / <code>False</code></li>
</ul>
<blockquote>Bonne pratique : donnez des noms explicites (<code>prix_total</code> plutôt que <code>x</code>).</blockquote>
""")

bloc(s11, 2, "Déclarer et utiliser des variables", "code", langage_code="python", duree_estimee_minutes=8,
     code_source="""# Variables et types
prenom = "Awa"          # str
age = 21                # int
taille = 1.68           # float
inscrit = True          # bool

print(type(prenom))     # <class 'str'>
print(f"{prenom} a {age} ans.")

# Opérations
prix = 19.99
quantite = 3
total = prix * quantite
print("Total :", round(total, 2), "€")  # Total : 59.97 €

# Les chaînes sont concaténables et répétables
salutation = "Bonjour" + " " + prenom
separateur = "-" * 20
print(salutation)
print(separateur)
""")

bloc(s11, 3, "Vidéo — Python en 100 secondes", "video", duree_estimee_minutes=2,
     video_url="https://www.youtube.com/watch?v=x7X9w_GIm1s")
bloc(s11, 4, "Documentation officielle — Introduction", "lien", duree_estimee_minutes=15,
     lien_externe="https://docs.python.org/fr/3/tutorial/introduction.html")

quiz(s11, "Quiz — Variables et types", [
    ("Quel est le type de la valeur <code>3.14</code> en Python ?", [
        ("int", False), ("float", True), ("str", False), ("bool", False)]),
    ("Que vaut <code>7 // 2</code> en Python ?", [
        ("3.5", False), ("3", True), ("4", False), ("2", False)]),
    ("Quelle affirmation est correcte concernant Python ?", [
        ("Il faut déclarer le type avant d'utiliser une variable", False),
        ("Le type d'une variable est déduit automatiquement de sa valeur", True),
        ("Une variable ne peut jamais changer de valeur", False),
        ("Les chaînes ne peuvent pas être concaténées", False)]),
])

s12 = Sequence.objects.create(module=m1, titre="Conditions et boucles", ordre=2,
                              description="Prendre des décisions et répéter des traitements.")
bloc(s12, 1, "Les structures conditionnelles", "texte", duree_estimee_minutes=12, contenu_html="""
<h3>Conditions : if / elif / else</h3>
<p>Une condition exécute un bloc seulement si une expression est vraie :</p>
<pre><code>note = 14
if note >= 16:
    mention = "Très bien"
elif note >= 14:
    mention = "Bien"
elif note >= 10:
    mention = "Admis"
else:
    mention = "Insuffisant"
</code></pre>
<p>En Python, <strong>l'indentation fait partie de la syntaxe</strong> : elle délimite les blocs.</p>
<h3>Boucles</h3>
<ul>
  <li><code>for</code> : parcourir une séquence (liste, chaîne, <code>range</code>).</li>
  <li><code>while</code> : répéter tant qu'une condition est vraie.</li>
</ul>
""")
bloc(s12, 2, "Conditions et boucles — exemples", "code", langage_code="python", duree_estimee_minutes=10,
     code_source="""# if / elif / else
temperature = 31
if temperature > 30:
    print("Il fait chaud")
elif temperature > 18:
    print("Temps agréable")
else:
    print("Il fait frais")

# Boucle for
for i in range(1, 6):
    print("Tour", i)

# Boucle while
compteur = 3
while compteur > 0:
    print("Décollage dans", compteur)
    compteur -= 1
print("Décollage !")

# break / continue
for n in range(1, 11):
    if n % 2 == 0:
        continue          # ignorer les pairs
    if n > 7:
        break             # arrêter après 7
    print("Impair :", n)
""")
fichier_pdf = make_pdf("Fiche memo - Conditions et boucles", [
    "if / elif / else : execute un bloc selon une condition.",
    "for : parcourt une sequence (liste, chaine, range).",
    "while : repete tant que la condition est vraie.",
    "break : quitte la boucle ; continue : passe a l'iteration suivante.",
    "L'indentation delimite les blocs en Python.",
])
bloc(s12, 3, "Fiche mémo — Conditions & boucles (PDF)", "fichier", duree_estimee_minutes=5,
     fichier=ContentFile(fichier_pdf, 'memo_conditions_boucles.pdf') if False else None)
# (le contenu fichier est affecté proprement ci-dessous)
b_pdf = BlocContenu.objects.get(sequence=s12, titre="Fiche mémo — Conditions & boucles (PDF)")
b_pdf.fichier.save('memo_conditions_boucles.pdf', ContentFile(fichier_pdf), save=True)

quiz(s12, "Quiz — Conditions et boucles", [
    ("Quelle instruction permet de répéter un bloc tant qu'une condition est vraie ?", [
        ("if", False), ("while", True), ("def", False), ("return", False)]),
    ("Que fait l'instruction <code>break</code> dans une boucle ?", [
        ("Passe à l'itération suivante", False), ("Quitte immédiatement la boucle", True),
        ("Redémarre la boucle", False), ("Lève une erreur", False)]),
    ("En Python, comment délimite-t-on un bloc de code ?", [
        ("Avec des accolades { }", False), ("Avec l'indentation", True),
        ("Avec begin / end", False), ("Avec des parenthèses", False)]),
])

# ═══════════════════════════ MODULE 2 ═══════════════════════════
m2 = Module.objects.create(cours=cours, titre="Module 2 — Fonctions et structures de données", ordre=2,
                           duree_estimee=240,
                           description="Organiser son code avec des fonctions et manipuler des collections.")

s21 = Sequence.objects.create(module=m2, titre="Les fonctions", ordre=1,
                              description="Réutiliser du code et structurer un programme.")
bloc(s21, 1, "Définir et appeler une fonction", "texte", duree_estimee_minutes=12, contenu_html="""
<h3>Pourquoi des fonctions ?</h3>
<p>Une fonction regroupe un traitement réutilisable. On la définit avec <code>def</code> :</p>
<pre><code>def aire_rectangle(largeur, hauteur):
    return largeur * hauteur
</code></pre>
<ul>
  <li><strong>Paramètres</strong> : valeurs reçues (<code>largeur</code>, <code>hauteur</code>).</li>
  <li><strong>return</strong> : valeur renvoyée à l'appelant.</li>
  <li>Une fonction sans <code>return</code> renvoie <code>None</code>.</li>
</ul>
""")
bloc(s21, 2, "Fonctions — paramètres et valeur de retour", "code", langage_code="python", duree_estimee_minutes=9,
     code_source="""def saluer(prenom, formalite="Bonjour"):
    return f"{formalite}, {prenom} !"

print(saluer("Awa"))                 # Bonjour, Awa !
print(saluer("Moussa", "Salut"))     # Salut, Moussa !

def moyenne(notes):
    if not notes:
        return 0
    return sum(notes) / len(notes)

print("Moyenne :", round(moyenne([12, 15, 9, 18]), 2))

# Fonction lambda (anonyme)
carre = lambda x: x * x
print([carre(n) for n in range(1, 6)])   # [1, 4, 9, 16, 25]
""")
bloc(s21, 3, "Documentation — Définir des fonctions", "lien", duree_estimee_minutes=10,
     lien_externe="https://docs.python.org/fr/3/tutorial/controlflow.html#defining-functions")
quiz(s21, "Quiz — Les fonctions", [
    ("Quel mot-clé définit une fonction en Python ?", [
        ("function", False), ("def", True), ("func", False), ("lambda", False)]),
    ("Que renvoie une fonction qui ne contient aucun <code>return</code> ?", [
        ("0", False), ("None", True), ("False", False), ("Une erreur", False)]),
    ("Quelle est la valeur de <code>aire_rectangle(3, 4)</code> si la fonction renvoie <code>largeur * hauteur</code> ?", [
        ("7", False), ("12", True), ("34", False), ("1", False)]),
])

s22 = Sequence.objects.create(module=m2, titre="Listes, tuples et dictionnaires", ordre=2,
                              description="Stocker plusieurs valeurs et y accéder efficacement.")
bloc(s22, 1, "Manipuler des collections", "texte", duree_estimee_minutes=12, contenu_html="""
<h3>Les collections en Python</h3>
<ul>
  <li><strong>list</strong> : ordonnée et modifiable — <code>[1, 2, 3]</code></li>
  <li><strong>tuple</strong> : ordonné et non modifiable — <code>(1, 2, 3)</code></li>
  <li><strong>dict</strong> : clés → valeurs — <code>{"nom": "Awa"}</code></li>
</ul>
<pre><code>notes = [12, 15, 9]
notes.append(18)          # ajouter
notes[0] = 13             # modifier
moyenne = sum(notes) / len(notes)
</code></pre>
""")
bloc(s22, 2, "Collections — exemples", "code", langage_code="python", duree_estimee_minutes=10,
     code_source="""# Liste
notes = [12, 15, 9, 18]
notes.append(14)
print("Notes :", notes, "| max :", max(notes))

# Parcours
for note in notes:
    print(note, "->", "Admis" if note >= 10 else "Recalé")

# Tuple (immuable)
coordonnees = (14.69, -17.44)
lat, lon = coordonnees          # dépaquetage
print("Latitude :", lat)

# Dictionnaire
etudiants = {"Awa": 15, "Moussa": 12}
etudiants["Fatou"] = 17
for nom, note in etudiants.items():
    print(f"{nom} : {note}/20")
""")
pdf_memo = make_pdf("Memento Python - structures de donnees", [
    "list : [1, 2, 3] -> ordonnee, modifiable (append, remove).",
    "tuple : (1, 2, 3) -> ordonne, immuable.",
    "dict : {'cle': 'valeur'} -> acces par cle, parcours avec .items().",
    "set : {1, 2, 3} -> valeurs uniques, non ordonne.",
    "Fonctions utiles : len, sum, max, min, sorted.",
])
b_res = RessourceSequence(sequence=s22, titre="Mémento Python — structures de données",
                          description="Aide-mémoire PDF sur les collections Python.",
                          type_ressource='pdf', ordre=1)
b_res.fichier.save('memento_python_structures.pdf', ContentFile(pdf_memo), save=True)
b_res.taille_fichier = len(pdf_memo)
b_res.save()

quiz(s22, "Quiz — Structures de données", [
    ("Quelle structure associe des clés à des valeurs ?", [
        ("list", False), ("tuple", False), ("dict", True), ("set", False)]),
    ("Quelle méthode ajoute un élément à la fin d'une liste ?", [
        ("add()", False), ("append()", True), ("push()", False), ("insert()", False)]),
    ("Quelle affirmation est vraie pour un tuple ?", [
        ("Il est modifiable", False), ("Il est immuable", True),
        ("Il accepte des clés", False), ("Il n'est pas ordonné", False)]),
])

# ═══════════════════════════ MODULE 3 ═══════════════════════════
m3 = Module.objects.create(cours=cours, titre="Module 3 — Développement Web avec Flask", ordre=3,
                           duree_estimee=300,
                           description="Créer une première application web : routes, templates, formulaires.")

s31 = Sequence.objects.create(module=m3, titre="HTTP et routes Flask", ordre=1,
                              description="Comprendre le dialogue client/serveur et créer des routes.")
bloc(s31, 1, "Comment fonctionne le web ?", "texte", duree_estimee_minutes=12, contenu_html="""
<h3>Client, serveur et HTTP</h3>
<p>Votre navigateur (le <strong>client</strong>) envoie une requête <strong>HTTP</strong> à un
<strong>serveur</strong>, qui renvoie une réponse :</p>
<ul>
  <li><code>GET</code> : demander une ressource (une page).</li>
  <li><code>POST</code> : envoyer des données (un formulaire).</li>
</ul>
<p>Une <strong>route</strong> associe une URL à une fonction Python. <strong>Flask</strong> est un
micro-framework qui rend cela très simple.</p>
""")
blob = """from flask import Flask

app = Flask(__name__)

@app.route("/")
def accueil():
    return "<h1>Bienvenue sur mon site</h1>"

@app.route("/bonjour/<prenom>")
def bonjour(prenom):
    return f"Bonjour {prenom} !"

if __name__ == "__main__":
    app.run(debug=True)
"""
bloc(s31, 2, "Une première application Flask", "code", langage_code="python", duree_estimee_minutes=12,
     code_source=blob)
bloc(s31, 3, "Vidéo — Flask pour débutants", "video", duree_estimee_minutes=15,
     video_url="https://www.youtube.com/watch?v=Z1RJmh_OqeA")
bloc(s31, 4, "Documentation — Démarrage rapide Flask", "lien", duree_estimee_minutes=15,
     lien_externe="https://flask.palletsprojects.com/en/stable/quickstart/")
quiz(s31, "Quiz — HTTP et Flask", [
    ("Quelle méthode HTTP utilise-t-on pour envoyer un formulaire ?", [
        ("GET", False), ("POST", True), ("PUT", False), ("HEAD", False)]),
    ("En Flask, quel décorateur associe une URL à une fonction ?", [
        ("@app.route", True), ("@app.url", False), ("@app.get", False), ("@app.path", False)]),
    ("Que renvoie une fonction de vue Flask lorsqu'elle renvoie une chaîne ?", [
        ("Un fichier", False), ("Une réponse HTTP avec cette chaîne comme corps", True),
        ("Un JSON", False), ("Rien", False)]),
])

s32 = Sequence.objects.create(module=m3, titre="Templates Jinja2 et formulaires", ordre=2,
                              description="Séparer la logique de la présentation et gérer les données.")
bloc(s32, 1, "Afficher des données dynamiques", "texte", duree_estimee_minutes=12, contenu_html="""
<h3>Templates Jinja2</h3>
<p>Plutôt que de concaténer du HTML en Python, on utilise un <strong>template</strong> :</p>
<pre><code>&lt;h1&gt;Bonjour {{ prenom }}&lt;/h1&gt;
&lt;ul&gt;
{% for note in notes %}
  &lt;li&gt;{{ note }}&lt;/li&gt;
{% endfor %}
&lt;/ul&gt;
</code></pre>
<p><code>{{ ... }}</code> affiche une variable, <code>{% for %}</code> répète un bloc.</p>
""")
bloc(s32, 2, "Routes + template + formulaire", "code", langage_code="python", duree_estimee_minutes=14,
     code_source="""from flask import Flask, render_template, request

app = Flask(__name__)

NOTES = []

@app.route("/", methods=["GET", "POST"])
def accueil():
    if request.method == "POST":
        note = request.form.get("note")
        if note:
            NOTES.append(int(note))
    moyenne = sum(NOTES) / len(NOTES) if NOTES else 0
    return render_template("index.html", notes=NOTES, moyenne=round(moyenne, 2))

if __name__ == "__main__":
    app.run(debug=True)
""")
bloc(s32, 3, "Vidéo — Templates Flask (Jinja2)", "video", duree_estimee_minutes=12,
     video_url="https://www.youtube.com/watch?v=QnDWIZuWYW0")
quiz(s32, "Quiz — Templates et formulaires", [
    ("Quelle syntaxe Jinja2 affiche une variable ?", [
        ("{{ variable }}", True), ("{% variable %}", False), ("[[ variable ]]", False), ("< variable >", False)]),
    ("Quelle directive Jinja2 répète un bloc ?", [
        ("{% repeat %}", False), ("{% for ... %}", True), ("{% loop %}", False), ("{% each %}", False)]),
    ("En Flask, comment récupérer une donnée envoyée en POST ?", [
        ("request.args", False), ("request.form", True), ("request.json", False), ("request.body", False)]),
])

# ── Inscription + suivi de l'apprenant ───────────────────────────────────────
insc, _ = InscriptionCours.objects.get_or_create(apprenant=appr, cours=cours)
insc.statut = 'en_cours'
insc.save()
Suivi.objects.get_or_create(apprenant=appr, cours=cours, defaults={'progression': 0})

# ── Recommandations avec VRAIS contenus générés ──────────────────────────────
RecommandationPedagogique.objects.filter(apprenant=appr, cours=cours).delete()
ContenuGenere.objects.filter(apprenant=appr, sequence_source__module__cours=cours).delete()

seq_cond = Sequence.objects.get(module=m1, titre="Conditions et boucles")
bloc_cond = BlocContenu.objects.get(sequence=seq_cond, titre="Conditions et boucles — exemples")

req = AIAnalysisRequest.objects.create(
    apprenant=appr, cours=cours, bloc=bloc_cond, sequence=seq_cond,
    trigger='quiz_rate', status='success', tokens_used=0,
)

contenu1 = ContenuGenere.objects.create(
    ai_request=req, apprenant=appr, type_contenu='bloc_simplifie',
    titre="Les boucles expliquées simplement",
    description="Reprise pas à pas des boucles for et while avec un exemple concret.",
    sequence_source=seq_cond, bloc_source=bloc_cond,
    niveau_difficulte='debutant',
    concepts_cibles=['boucles', 'for', 'while', 'range'],
    contenu_html="""
<h3>Comprendre les boucles, pas à pas</h3>
<p>Une <strong>boucle</strong> sert à répéter une action sans réécrire le code.</p>
<p><strong>1. La boucle <code>for</code></strong> — répéter un nombre connu de fois :</p>
<pre><code>for i in range(3):
    print("Bonjour", i)
# Bonjour 0 / Bonjour 1 / Bonjour 2
</code></pre>
<p><strong>2. La boucle <code>while</code></strong> — répéter tant qu'une condition est vraie :</p>
<pre><code>energie = 3
while energie > 0:
    print("Encore", energie)
    energie -= 1
</code></pre>
<blockquote>Astuce : si votre boucle ne s'arrête jamais, vérifiez que la condition finit par devenir fausse.</blockquote>
<p>Entraînez-vous : affichez les nombres pairs de 1 à 20 avec une boucle.</p>
""",
)

reco1 = RecommandationPedagogique.objects.create(
    apprenant=appr, cours=cours, sequence_cible=seq_cond, bloc_cible=bloc_cond,
    contenu_genere=contenu1, type_recommandation='bloc_revoir', priorite=1,
    message="Vous avez eu des difficultés sur « Conditions et boucles ». Une reprise simplifiée, avec des exemples de for et while, est prête.",
)

contenu2 = ContenuGenere.objects.create(
    ai_request=req, apprenant=appr, type_contenu='bloc_alternatif',
    titre="Les fonctions vues autrement",
    description="Analogie et exemple concret pour comprendre les fonctions.",
    sequence_source=Sequence.objects.get(module=m2, titre="Les fonctions"),
    niveau_difficulte='debutant',
    concepts_cibles=['fonctions', 'paramètres', 'return'],
    contenu_html="""
<h3>Une fonction, c'est une recette</h3>
<p>Imaginez une recette de cuisine : vous donnez des <strong>ingrédients</strong> (paramètres)
et vous obtenez un <strong>plat</strong> (la valeur de retour).</p>
<pre><code>def jus(fruit, sucre=2):
    return f"Jus de {fruit} avec {sucre} morceaux de sucre"

print(jus("mangue"))          # Jus de mangue avec 2 morceaux de sucre
print(jus("orange", 1))       # Jus d'orange avec 1 morceaux de sucre
</code></pre>
<p>Réutiliser une fonction évite de dupliquer la logique et rend le code plus lisible.</p>
""",
)

reco2 = RecommandationPedagogique.objects.create(
    apprenant=appr, cours=cours, sequence_cible=contenu2.sequence_source, contenu_genere=contenu2,
    type_recommandation='contenu_alternatif', priorite=2,
    message="Une autre façon d'aborder « Les fonctions » (analogie de la recette) est disponible.",
)

print("OK cours=", cours.id, "modules=", Module.objects.filter(cours=cours).count(),
      "sequences=", Sequence.objects.filter(module__cours=cours).count(),
      "blocs=", BlocContenu.objects.filter(sequence__module__cours=cours).count(),
      "quiz=", Quiz.objects.filter(sequence__module__cours=cours).count(),
      "questions=", Question.objects.filter(quiz__sequence__module__cours=cours).count())
print("OK inscription=", insc.id, "apprenant=", appr.id, appr.prenom, appr.nom)
print("OK recos=", RecommandationPedagogique.objects.filter(apprenant=appr, cours=cours).count())
