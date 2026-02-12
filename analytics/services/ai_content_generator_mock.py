import random
from analytics.models import ContenuGenere, QuestionAnalytics

class AIContentGeneratorMock:
    """
    Version simulée de l'AI Content Generator
    Génère du contenu factice pour les tests
    """
    
    def __init__(self):
        self.templates_remediation = [
            """
            <h3>Comprendre ce concept autrement</h3>
            <p>Imaginons que vous préparez un gâteau. Les <strong>variables</strong> sont comme 
            les ingrédients : vous pouvez changer la quantité de farine, de sucre, etc.</p>
            
            <h4>Exercice guidé :</h4>
            <ol>
                <li>Créez une variable pour stocker votre âge</li>
                <li>Affichez cette variable</li>
                <li>Modifiez sa valeur</li>
            </ol>
            
            <p><em>Conseil : Une variable est juste une boîte avec un nom où on met quelque chose.</em></p>
            """,
            """
            <h3>Approche simplifiée</h3>
            <p>Pensez aux <strong>boucles</strong> comme à un manège : tant que vous avez des tickets, 
            vous pouvez faire un tour de plus !</p>
            
            <h4>Mini-exercice :</h4>
            <ul>
                <li>Affichez les nombres de 1 à 5</li>
                <li>À chaque tour, le compteur augmente</li>
                <li>Quand on arrive à 5, on s'arrête</li>
            </ul>
            
            <p><strong>Astuce :</strong> C'est exactement comme compter sur vos doigts !</p>
            """,
        ]
        
        self.templates_alternative = [
            """
            <h3>Une autre façon de voir les choses</h3>
            <p>Au lieu de voir ça comme du code, pensez-y comme à une recette de cuisine :</p>
            
            <ol>
                <li><strong>Ingrédients</strong> = Variables</li>
                <li><strong>Instructions</strong> = Code</li>
                <li><strong>Résultat</strong> = Output</li>
            </ol>
            
            <h4>Exemple concret :</h4>
            <p>Si vous voulez faire une salade, vous prenez des tomates (variable), 
            vous les coupez (fonction), et vous obtenez une salade prête (résultat).</p>
            """,
            """
            <h3>Changeons d'angle</h3>
            <p>Imaginez que vous construisez avec des LEGO 🧱</p>
            
            <ul>
                <li>Chaque brique = une instruction</li>
                <li>L'assemblage = votre programme</li>
                <li>La construction finale = le résultat</li>
            </ul>
            
            <p><em>Vous ne construisez pas tout d'un coup, vous empilez brique par brique !</em></p>
            """,
        ]
    
    def generer_remediation(self, apprenant, question_ratee, bloc_source):
        """
        Génère un contenu de remédiation simulé
        """
        from analytics.models import ContenuGenere, QuestionAnalytics
        
        analytics = QuestionAnalytics.objects.filter(
            apprenant=apprenant,
            question=question_ratee
        ).first()
        
        # Choisir un template aléatoire
        contenu_html = random.choice(self.templates_remediation)
        
        # Personnaliser avec le titre de la question
        titre = f"💡 Comprendre : {question_ratee.enonce_texte[:50]}..."
        
        contenu_genere = ContenuGenere.objects.create(
            apprenant=apprenant,
            bloc_source=bloc_source,
            type_generation='remediation',
            titre=titre,
            contenu_html=contenu_html,
            concepts_cibles=analytics.concepts_fragiles if analytics else ['concept_base'],
            niveau_difficulte=2
        )
        
        print(f"✅ [MOCK] Contenu de remédiation généré : {titre}")
        return contenu_genere
    
    def generer_approche_alternative(self, apprenant, bloc_source):
        """
        Génère une approche alternative simulée
        """
        from analytics.models import ContenuGenere
        
        contenu_html = random.choice(self.templates_alternative)
        
        titre = f"🔄 Autre façon de voir : {bloc_source.titre}"
        
        contenu_genere = ContenuGenere.objects.create(
            apprenant=apprenant,
            bloc_source=bloc_source,
            type_generation='alternative',
            titre=titre,
            contenu_html=contenu_html,
            niveau_difficulte=2
        )
        
        print(f"✅ [MOCK] Approche alternative générée : {titre}")
        return contenu_genere