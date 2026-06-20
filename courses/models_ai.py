# courses/models_ai.py
# ============================================================================
# PROXY IA — Réexporte les modèles d'analaytics.models
# Les vrais modèles (AIAnalysisRequest, ContenuGenere, QuizGenereClaude)
# sont définis dans analytics.models
# ============================================================================

from analytics.models import (
    AIAnalysisRequest,
    ContenuGenere,
    QuizGenereClaude,
)

__all__ = [
    'AIAnalysisRequest',
    'ContenuGenere',
    'QuizGenereClaude',
]