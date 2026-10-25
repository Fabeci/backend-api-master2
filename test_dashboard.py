#!/usr/bin/env python
"""
Test script for admin dashboards.
Tests that all dashboard URLs are accessible with proper authentication.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User

# Test accounts (from seed_clean.py)
TEST_ACCOUNTS = [
    ('superadmin1@sma.pro', 'SuperAdmin'),
    ('admin1@sma.pro', 'Admin'),
    ('resp1@sma.pro', 'Responsable'),
    ('form1@sma.pro', 'Formateur'),
    ('parent1@sma.pro', 'Parent'),
    ('app1@sma.pro', 'Apprenant'),
]

DASHBOARD_URLS = [
    '/admin/dashboard/',
    '/admin/dashboard/superadmin/',
    '/admin/dashboard/admin/',
    '/admin/dashboard/formateur/',
    '/admin/dashboard/parent/',
    '/admin/dashboard/responsable/',
    '/admin/dashboard/apprenant/',
]

def test_dashboards():
    client = Client()

    for email, role in TEST_ACCOUNTS:
        print(f"\n{'='*60}")
        print(f"Testing as: {email} ({role})")
        print(f"{'='*60}")

        # Login
        logged_in = client.login(username=email, password='password123')
        if not logged_in:
            print(f"  [FAIL] Login FAILED for {email}")
            continue

        print(f"  [OK] Logged in as {email}")

        # Test each dashboard URL
        for url in DASHBOARD_URLS:
            response = client.get(url)
            status = response.status_code
            if status == 200:
                print(f"  [OK] {url} -> 200")
            else:
                print(f"  [FAIL] {url} -> {status} (expected 200)")

        client.logout()

    print(f"\n{'='*60}")
    print("Dashboard tests completed.")
    print(f"{'='*60}")

if __name__ == '__main__':
    test_dashboards()
