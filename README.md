# Fleet Router

A small Django/DRF service that acts as a **fleet fueling optimizer**: it exposes a REST API, and  will call an external raw map and routing API, processes the response to find optimal fuel stops from known gas stations (optmizes by max range and fuel price), then returns the optimized route and refueling stops map to the caller.

## How it works

1. On start, the fuel stations CSV data is loaded into the database, and each station gets the coordinate of the city it belongs to using another US cities CSV
2. **You call the endpoint** with a start and finish location:
  `GET /api/route_map/?start=Chicago,%20IL&finish=Denver,%20CO`
3. **The API checks its cache.** If this exact trip was planned before, it returns the stored answer immediately.
4. **It converts both locations into coordinates** using a geocoding service (Nominatim), turning "Chicago, IL" into a latitude/longitude pair.
5. **It asks OSRM for the driving route** — the full path of the trip as a list of coordinates, plus which highways the route uses.
6. **It narrows down the fuel stations.** Out of 8K stations in the CSV, it keeps only the ones in states the route passes through.
7. **It walks the route and picks fuel stops.** Starting from the beginning, it tracks how far the car has driven. When the remaining distance exceeds 500 miles (with a 10% safety buffer), it looks for the cheapest station near the furthest point it can still reach, and marks it as a stop. It repeats this until the destination fits within one tank.
8. **It calculates the total cost.** Each leg of the trip is charged at the price per gallon of the station the car refueled at before that leg, using the reference MPG and the computed leg distance.
9. **It returns the answer**: the route coordinates to draw on a map, the list of fuel stops with their names, prices, and distances, plus the total miles and total fuel cost.

The first request for a new trip takes a few seconds because the geocoding and routing services are rate-limited to one call per second. Every repeat request is instant, and any new trip that passes near stations already looked up reuses those coordinates for free, and previously computed routes are cached as well.     

### Initial assumptions and design choices

- We assume that the truck/car is fully loaded on fuel at start.
- Each fuel station gets the centroid coordinates of the city it belongs to.
- All internal calculations are in metrics units, the MPG and MAX RANGE are in miles for user reference, and they are internally converted to meters/km.



### Roadmap

- [x] Add `FuelStation` and `CachedRoute` models and migrations
- [x] Register models in the Django admin
- [x] Implement external API calls and refuel stations optimizer
- [x] Add tests for the refuel stops optimizer service layer
- [ ] Gracefully handle the network timeout errors when calling OSRM or Nominatim APIs in the main endpoint call result.

---



## The Project



### Prerequisites

- Docker Engine 24+ and Docker Compose v2 (`docker compose`, not `docker-compose`)
- Optional, only for local (non-Docker) runs: Python 3.14

Verify:

```bash
docker --version
docker compose version
```



### Stack


| Layer            | Choice                     |
| ---------------- | -------------------------- |
| Language         | Python 3.14                |
| Web framework    | Django 6.1                 |
| API framework    | Django REST Framework 3.18 |
| HTTP client      | `requests`                 |
| Server           | Gunicorn                   |
| Database         | SQLite (volume-backed)     |
| Containerization | Docker + Docker Compose    |




### Persistence

SQLite lives at `/app/data/db.sqlite3` inside the container, backed by the
named Docker volume `sqlite_data`. This means:

- The database survives `docker compose down` and `docker compose up`.
- The database is **deleted** by `docker compose down -v` (the `-v` removes
volumes).
- The local `./data/db.sqlite3` file is intentionally git-ignored.



### Configuration

Environment variables are read from `.env` (see `.env.example`):


| Variable                | Purpose                                          | Default          |
| ----------------------- | ------------------------------------------------ | ---------------- |
| `DJANGO_SECRET_KEY`     | Django secret key — set a real one in production | `unsafe-default` |
| `DJANGO_DEBUG`          | `True` / `False`                                 | `False`          |
| `DJANGO_ALLOWED_HOSTS`  | Comma-separated hostnames                        | `localhost`      |
| `EXTERNAL_API_BASE_URL` | Base URL of the external API (empty for now)     | *(empty)*        |
| `EXTERNAL_API_TIMEOUT`  | External API request timeout in seconds          | `10`             |


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

1. Runs `python manage.py migrate` - creates the SQLite database and all
  built-in Django tables (auth, sessions, admin, content types).
2. Runs `python manage.py collectstatic` - gathers admin static assets.
3. Runs `python manage.py load_fuel_stations_csv` - import the known fueling stations from the /data/fuel-prices-for-be-assessment.csv file
4. Starts Gunicorn on port `8000`.

Check that it came up:

```bash
docker compose ps
docker compose logs -f web
```



### Alt. Running without Docker (optional)

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

---



## Verifying it works



### API endpoints check

```bash
# Health check
curl http://localhost:8000/api/health/
# -> {"status": "ok"}

# Placeholder bridge endpoint (dummy JSON for now)
curl http://localhost:8000/api/route_map/?start=Chicago,%20IL&finish=Detroit,%20MI
# -> {"start":{"query":"Chicago, IL","lat":41.8755616,"lon":-87.6244212},"finish":{"query":"Detroit, MI","lat":42.3315509,"lon":-83.0466403},"route":[[41.875563,-87.624351],[41.875314,-87.624346],[41.875125,-87.624342],[41.874667,-87.624334],[41.874574,-87.624331],[41.874452,-87.624328],[41.874447,-87.624449],[41.874447,-87.624484],[41.874428,-87.625165],[41.874427,-87.625224],[41.874422,-87.625509],[41.874418,-87.625846],[41.874414,-87.625988],[41.87441,-87.626166],[41.874406] ...}
```

You can also open the DRF browsable API in a browser: [http://localhost:8000/api/route_map/](http://localhost:8000/api/bridge/)  or use Postman API client.





### Django admin

The admin is enabled at [http://localhost:8000/admin/](http://localhost:8000/admin/).

Create a superuser (one time):

```bash
docker compose exec web python manage.py createsuperuser
```

Log in with the credentials you just set.





### Common dev commands

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



## API endpoints


| Method | Path                     | Description                                                                                  |
| ------ | ------------------------ | -------------------------------------------------------------------------------------------- |
| GET    | `/api/health/`           | Liveness probe — returns `{"status": "ok"}`                                                  |
| GET    | `/api/route_map/`        | Placeholder endpoint returning dummy JSON                                                    |
| GET    | `/admin/`                | Django admin UI                                                                              |
| GET    | `/api/stats`             | Reports how many fuel stations are in the DB, and how many of them have been geocoded so far |
| GET    | `/api/debug/cache-stats` | Exposes the in-process counters from external API services                                   |


---



## Tests

The test coverage includes 2 scenarios:

- Scenario 1 — short trip, under range, no refueling stops, zero cost.
- Scenario 2 — long trip, over range, requires refueling stops.

No network calls are made during the tests. Sandboxing and factory fixtures, mocks and stubs are used instead.

Run those tests with `docker compose exec web python -m pytest`
