import anthropic
from django.conf import settings

class AIContentGenerator:
    def __init__(self):
        # ✅ Version simplifiée sans paramètres problématiques
        self.client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
    
    def generer_remediation(self, apprenant, question_ratee, bloc_source):
        """
        Génère un contenu de remédiation après échec à une question
        """
        from analytics.models import ContenuGenere, QuestionAnalytics
        
        analytics = QuestionAnalytics.objects.filter(
            apprenant=apprenant,
            question=question_ratee
        ).first()
        
        # Construire le prompt
        prompt = f"""Tu es un expert pédagogique. Un apprenant a échoué à cette question :

**Question** : {question_ratee.enonce_texte}
**Nombre d'échecs** : {analytics.nombre_echecs if analytics else 1}
**Concepts fragiles** : {analytics.concepts_fragiles if analytics else 'N/A'}

**Contenu original du bloc** :
{bloc_source.contenu_texte[:500] if bloc_source.contenu_texte else bloc_source.contenu_html[:500]}...

Génère un contenu pédagogique de remédiation court et efficace :
1. Explique le concept de manière très simple avec des exemples concrets
2. Utilise une analogie du quotidien
3. Propose un mini-exercice guidé pas-à-pas
4. Limite à 300 mots maximum

Format : HTML simple (p, ul, li, strong, em uniquement)
Ne mets PAS de balises ```html au début ou à la fin."""
        
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            contenu_html = message.content[0].text
            
            # Nettoyer le contenu (enlever les balises markdown si présentes)
            contenu_html = contenu_html.replace('```html', '').replace('```', '').strip()
            
            # Sauvegarder le contenu généré
            contenu_genere = ContenuGenere.objects.create(
                apprenant=apprenant,
                bloc_source=bloc_source,
                type_generation='remediation',
                titre=f"💡 Comprendre : {question_ratee.enonce_texte[:50]}...",
                contenu_html=contenu_html,
                concepts_cibles=analytics.concepts_fragiles if analytics else [],
                niveau_difficulte=2
            )
            
            print(f"✅ Contenu de remédiation généré : {contenu_genere.titre}")
            return contenu_genere
        
        except Exception as e:
            print(f"❌ Erreur génération IA: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def generer_approche_alternative(self, apprenant, bloc_source):
        """
        Génère une approche alternative quand l'apprenant est bloqué
        """
        from analytics.models import ContenuGenere
        
        prompt = f"""Un apprenant passe beaucoup de temps sur ce bloc sans progresser :

**Titre** : {bloc_source.titre}
**Type** : {bloc_source.get_type_bloc_display()}
**Contenu actuel** :
{bloc_source.contenu_texte[:500] if bloc_source.contenu_texte else bloc_source.contenu_html[:500]}...

Propose une approche pédagogique DIFFÉRENTE pour expliquer le même concept :
- Si c'était du texte abstrait → propose avec métaphores concrètes
- Si c'était technique → propose des exemples du quotidien
- Change complètement l'angle d'explication

Format : HTML simple (p, h3, h4, ul, li, strong, em uniquement)
Max 250 mots
Ne mets PAS de balises ```html au début ou à la fin."""
        
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            contenu_html = message.content[0].text
            
            # Nettoyer le contenu
            contenu_html = contenu_html.replace('```html', '').replace('```', '').strip()
            
            contenu_genere = ContenuGenere.objects.create(
                apprenant=apprenant,
                bloc_source=bloc_source,
                type_generation='alternative',
                titre=f"🔄 Autre façon de voir : {bloc_source.titre}",
                contenu_html=contenu_html,
                niveau_difficulte=2
            )
            
            print(f"✅ Approche alternative générée : {contenu_genere.titre}")
            return contenu_genere
        
        except Exception as e:
            print(f"❌ Erreur génération IA: {e}")
            import traceback
            traceback.print_exc()
            return None