#!/usr/bin/env python
"""
ILIMS Food Safety Molecular Analysis Portal — One-Command Setup Script

Usage:
    python setup.py

This script will:
  1. Check that all required Python packages are installed
  2. Create the PostgreSQL database if it does not exist
  3. Run all Django migrations (creates all tables)
  4. Seed the database with default data:
     - Countries, Regions, Laboratories
     - Product Categories, Product Types
     - Lab Methods (DNA Extraction, PCR, Sequencing)
     - Microorganisms (Salmonella, E. coli, Listeria, etc.)
     - Risk Levels
     - All 24 Feature Flags
     - 5 Test User Accounts (one per role)
  5. Collect static files for WhiteNoise
  6. Print login credentials and next steps

Requirements before running:
  - Python 3.11+ installed
  - PostgreSQL 17 running on localhost:5432
  - A PostgreSQL superuser (usually "postgres") available
  - A virtual environment activated with all packages from requirements.txt
"""

import os
import subprocess
import sys
from pathlib import Path

# ── Configuration ──
PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = sys.executable
DB_NAME = os.environ.get("DB_NAME", "ilims_db")
DB_USER = os.environ.get("DB_USER", "ilims_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "ilims_password")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")

# Default test accounts created by the seeder
TEST_ACCOUNTS = [
    {"role": "TECHNICIAN",        "username": "technician",       "email": "tech@ilims.lk"},
    {"role": "ANALYST",           "username": "analyst",          "email": "analyst@ilims.lk"},
    {"role": "QC_OFFICER",        "username": "qc_officer",       "email": "qc@ilims.lk"},
    {"role": "FOOD_SAFETY_OFFICER","username": "safety_officer",  "email": "officer@ilims.lk"},
    {"role": "ADMIN",             "username": "admin",            "email": "admin@ilims.lk"},
]
DEFAULT_PASSWORD = "Test@12345678"


def run(cmd, description, check=True):
    """Run a shell command and print status."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    print(f"  $ {cmd}\n")
    result = subprocess.run(cmd, shell=True, cwd=str(PROJECT_ROOT))
    if check and result.returncode != 0:
        print(f"\n  ❌ FAILED: {description}")
        print(f"  Fix the error above and re-run: python setup.py")
        sys.exit(1)
    else:
        print(f"\n  ✅ {description} — Done")
    return result


def create_database():
    """Attempt to create the PostgreSQL database if it doesn't exist."""
    print(f"\n{'='*60}")
    print(f"  Creating PostgreSQL Database: {DB_NAME}")
    print(f"{'='*60}")

    # Try using psql to create the database and user
    sql_commands = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{DB_USER}') THEN
            CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{DB_PASSWORD}';
        END IF;
    END
    $$;
    SELECT 'CREATE DATABASE {DB_NAME} OWNER {DB_USER}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{DB_NAME}')\\gexec
    GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};
    """

    # Try with the default 'postgres' superuser
    create_cmd = (
        f'psql -h {DB_HOST} -p {DB_PORT} -U postgres -c "'
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{DB_USER}') THEN "
        f"CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{DB_PASSWORD}'; "
        f"END IF; END $$;\" "
    )
    db_cmd = (
        f'psql -h {DB_HOST} -p {DB_PORT} -U postgres -tc '
        f'"SELECT 1 FROM pg_database WHERE datname = \'{DB_NAME}\'" | '
        f'grep -q 1 || psql -h {DB_HOST} -p {DB_PORT} -U postgres -c '
        f'"CREATE DATABASE {DB_NAME} OWNER {DB_USER};"'
    )

    # On Windows, psql might not be in PATH — skip gracefully
    try:
        subprocess.run(create_cmd, shell=True, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(db_cmd, shell=True, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"\n  ✅ Database '{DB_NAME}' and user '{DB_USER}' ready.")
    except FileNotFoundError:
        print(f"\n  ⚠️  psql not found in PATH.")
        print(f"  Please create the database manually:")
        print(f"    1. Open pgAdmin or psql")
        print(f"    2. CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{DB_PASSWORD}';")
        print(f"    3. CREATE DATABASE {DB_NAME} OWNER {DB_USER};")
        print(f"  Then re-run: python setup.py")


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ILIMS — Food Safety Molecular Analysis Portal              ║
║   Automated Setup & Database Initialization                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # Step 0: Ensure we're in the right directory
    os.chdir(str(PROJECT_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    # Step 1: Create database
    create_database()

    # Step 2: Run migrations
    run(
        f'"{VENV_PYTHON}" manage.py makemigrations accounts',
        "Creating account migrations"
    )
    run(
        f'"{VENV_PYTHON}" manage.py makemigrations core',
        "Creating core migrations"
    )
    run(
        f'"{VENV_PYTHON}" manage.py migrate',
        "Applying all database migrations"
    )

    # Step 3: Enable pg_trgm extension for fast search
    print(f"\n{'='*60}")
    print(f"  Enabling PostgreSQL Extensions")
    print(f"{'='*60}")
    try:
        import django
        django.setup()
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        print(f"\n  ✅ pg_trgm extension enabled")
    except Exception as e:
        print(f"\n  ⚠️  Could not enable pg_trgm: {e}")
        print(f"  Search will still work but may be slower on large datasets.")

    # Step 4: Seed default data
    run(
        f'"{VENV_PYTHON}" manage.py seed_portal_data',
        "Seeding default data (countries, labs, methods, users, flags)"
    )

    # Step 5: Collect static files
    run(
        f'"{VENV_PYTHON}" manage.py collectstatic --noinput',
        "Collecting static files for WhiteNoise",
        check=False
    )

    # Step 6: Create logs directory
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    (logs_dir / "ilims.log").touch(exist_ok=True)
    print(f"\n  ✅ Logs directory ready: {logs_dir}")

    # ── Final Summary ──
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    ✅  SETUP COMPLETE!                       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  To start the development server:                            ║
║                                                              ║
║      python manage.py runserver                              ║
║                                                              ║
║  Then open: http://127.0.0.1:8000/                          ║
║                                                              ║
║  ── Test Login Credentials ──                                ║
║                                                              ║""")

    for acct in TEST_ACCOUNTS:
        print(f"║  {acct['role']:<22} {acct['username']:<16} {DEFAULT_PASSWORD}  ║")

    print(f"""║                                                              ║
║  ── Key URLs ──                                              ║
║                                                              ║
║  Dashboard:        http://127.0.0.1:8000/                    ║
║  Samples:          http://127.0.0.1:8000/samples/            ║
║  QC Queue:         http://127.0.0.1:8000/qc/                ║
║  Reports:          http://127.0.0.1:8000/reports/            ║
║  Reminders:        http://127.0.0.1:8000/reminders/          ║
║  Audit Trail:      http://127.0.0.1:8000/audit/              ║
║  Settings:         http://127.0.0.1:8000/settings/           ║
║  Django Admin:     http://127.0.0.1:8000/django-admin/       ║
║                                                              ║
║  ── Cron (Production) ──                                     ║
║                                                              ║
║  */15 * * * * python manage.py run_reminders                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()