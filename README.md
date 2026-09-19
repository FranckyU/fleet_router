# Fleet Router

A small Django/DRF service that acts as a **fleet fueling optimizer**: it exposes a REST API, and  will call an external raw map and routing API, processes the response to find optimal fuel stops rom known gas stations (optmizes by max range and fuel price), then returns the refueling map to the caller.

The app is intentionally minimal right now — it exposes a health check and a
placeholder endpoint that returns dummy JSON. The external API integration and
data persistence will be added once the target API is known.

---

## Stack


| Layer            | Choice                     |
| ---------------- | -------------------------- |
| Language         | Python 3.14                |
| Web framework    | Django 6.1                 |
| API framework    | Django REST Framework 3.18 |
| HTTP client      | `requests`                 |
| Server           | Gunicorn                   |
| Database         | SQLite (volume-backed)     |
| Containerization | Docker + Docker Compose    |


---



## Project layout

```
fleet_router/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .dockerignore
├── .gitignore
├── manage.py
├── config/                    # Django project package (settings, urls, wsgi)
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── api/              # Django app (views, services, models, admin)
    ├── __init__.py
    ├── apps.py
    ├── admin.py
    ├── models.py
    ├── services.py
    ├── views.py
    ├── urls.py
    └── migrations/
        └── __init__.py
```

---



## Prerequisites

- Docker Engine 24+ and Docker Compose v2 (`docker compose`, not `docker-compose`)
- Optional, only for local (non-Docker) runs: Python 3.14

Verify:

```bash
docker --version
docker compose version
```

---



## Setup



### 1. Clone the repository

```bash
git clone <your-repo-url> fleet_router
cd fleet_router
```



### 2. Create your environment file

```bash
cp .env.example .env
```

Then edit `.env` and set at least `DJANGO_SECRET_KEY`. Leave
`EXTERNAL_API_BASE_URL` empty for now.

### 3. Build and start

```bash
docker compose up --build -d
```

On startup the container automatically:

1. Runs `python manage.py migrate` — creates the SQLite database and all
  built-in Django tables (auth, sessions, admin, content types).
2. Runs `python manage.py collectstatic` — gathers admin static assets.
3. Starts Gunicorn on port `8000`.

Check that it came up:

```bash
docker compose ps
docker compose logs -f web
```

---



## Verifying it works

```bash
# Health check
curl http://localhost:8000/api/health/
# -> {"status": "ok"}

# Placeholder bridge endpoint (dummy JSON for now)
curl http://localhost:8000/api/route_map/
# -> {"message": "route map endpoint is alive", "source": "dummy", "items": [...]}
```

You can also open the DRF browsable API in a browser: [http://localhost:8000/api/route_map/](http://localhost:8000/api/bridge/)

---



## Django admin

The admin is enabled at [http://localhost:8000/admin/](http://localhost:8000/admin/).

Create a superuser (one time):

```bash
docker compose exec web python manage.py createsuperuser
```

Log in with the credentials you just set. Nothing is registered in the admin
yet — that will change as models are added.

---



## Common commands

All management commands are run inside the running container:

```bash
# Django management commands
docker compose exec web python manage.py <command>

# Examples
docker compose exec web python manage.py shell
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py createsuperuser

# Make and apply migrations after adding a model to fleet_router/models.py
docker compose exec web python manage.py makemigrations api
docker compose exec web python manage.py migrate

# Logs
docker compose logs -f web

# Restart the app
docker compose restart web

# Stop the stack (database volume is preserved)
docker compose down

# Stop and wipe the database (irreversible)
docker compose down -v
```

---



## Persistence

SQLite lives at `/app/data/db.sqlite3` inside the container, backed by the
named Docker volume `sqlite_data`. This means:

- The database survives `docker compose down` and `docker compose up`.
- The database is **deleted** by `docker compose down -v` (the `-v` removes
volumes).
- The local `./data/` folder is intentionally git-ignored.

---



## Configuration

Environment variables are read from `.env` (see `.env.example`):


| Variable                | Purpose                                          | Default          |
| ----------------------- | ------------------------------------------------ | ---------------- |
| `DJANGO_SECRET_KEY`     | Django secret key — set a real one in production | `unsafe-default` |
| `DJANGO_DEBUG`          | `True` / `False`                                 | `False`          |
| `DJANGO_ALLOWED_HOSTS`  | Comma-separated hostnames                        | `localhost`      |
| `EXTERNAL_API_BASE_URL` | Base URL of the external API (empty for now)     | *(empty)*        |
| `EXTERNAL_API_TIMEOUT`  | External API request timeout in seconds          | `10`             |


Never commit `.env`. Only `.env.example` is tracked.

---



## API endpoints


| Method | Path              | Description                                 |
| ------ | ----------------- | ------------------------------------------- |
| GET    | `/api/health/`    | Liveness probe — returns `{"status": "ok"}` |
| GET    | `/api/route_map/` | Placeholder endpoint returning dummy JSON   |
| GET    | `/admin/`         | Django admin UI                             |


The `/api/bridge/` endpoint is where the external API call and data
processing will live once the target API is selected.

---



## Roadmap

- [ ] Add `ProcessedItem` model and migrations
- [ ] Implement external API call inside `/api/bridge/`
- [ ] Register models in the Django admin
- [ ] Add request/response serializers
- [ ] Add auth (token or session) if the API becomes private
- [ ] Add tests for the service layer and endpoints

---



## Running without Docker (optional)

If you have Python 3.14 locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
export DJANGO_SETTINGS_MODULE=config.settings

python manage.py migrate
python manage.py runserver
```

The app is then available at [http://localhost:8000/](http://localhost:8000/).