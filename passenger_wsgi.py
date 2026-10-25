# ============================================================================
# passenger_wsgi.py — point d'entrée cPanel (« Setup Python App »)
# C'est ce fichier que Passenger charge ; il ne doit PAS être déplacé.
# ============================================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "master_backend_api.settings")

from master_backend_api.wsgi import application  # noqa: E402,F401
