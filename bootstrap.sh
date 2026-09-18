#!/usr/bin/env bash
set -euo pipefail

# --- Create directory structure ---
mkdir -p config
mkdir -p api/migrations

# --- Create empty files ---
touch Dockerfile
touch docker-compose.yml
touch requirements.txt
touch .env.example
touch .dockerignore
touch manage.py

touch config/__init__.py
touch config/settings.py
touch config/urls.py
touch config/wsgi.py

touch api/__init__.py
touch api/apps.py
touch api/admin.py
touch api/models.py
touch api/services.py
touch api/views.py
touch api/urls.py
touch api/migrations/__init__.py

echo "Project skeleton created:"
find . -type f -o -type d | sort | sed 's|^\./||' | grep -v '^\.$'
