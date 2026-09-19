from api.exceptions import FuelDataNotLoaded, RoutePlanError
from api.models import FuelStation
from api.services import constants as C
from api.services.fuel_stations import (
    candidate_stations,
    cumulative_km,
    find_point_at_distance,
    haversine_km,
    route_bbox,
    sort_candidates_by_price,
    states_in_bbox,
    trim_by_price,
)
from api.services.geocoder import geocode_address
from api.services.osrm_client import get_route, highways_on_route


# ---------- search helpers ------------------------------------------------

def _find_cheapest_within(route_point, candidates, radius_km):
    """
    Return the cheapest candidate whose coordinates lie within `radius_km`
    of `route_point`, or (None, None).

    `candidates` is price-sorted, so the first hit is the cheapest.
    Every candidate is guaranteed to have coordinates (filtered at the
    queryset level in candidate_stations).
    """
    for s in candidates:
        d = haversine_km(route_point, (s.latitude, s.longitude))
        if d <= radius_km:
            return s, d
    return None, None


def _find_with_widening(route_point, candidates):
    for radius_km in C.WIDENING_RADII_KM:
        st, d = _find_cheapest_within(route_point, candidates, radius_km)
        if st is not None:
            return st, d
    return None, None


# ---------- public entry point --------------------------------------------

def plan_trip(start_query: str, finish_query: str) -> dict:
    if not FuelStation.objects.exists():
        raise FuelDataNotLoaded()

    start  = geocode_address(start_query)
    finish = geocode_address(finish_query)

    # ---- OSRM call #1: which highways does this route use? ----
    highways = highways_on_route(start, finish)

    # ---- OSRM call #2: full route geometry, fetched ONCE ----
    route     = get_route(start, finish)
    coords    = route["coords"]
    total_km  = route["distance_m"] / 1000.0
    cum       = cumulative_km(coords)

    # ---- Candidate narrowing (only pre-geocoded stations) ----
    bbox        = route_bbox(coords)
    state_codes = states_in_bbox(bbox)

    candidates = candidate_stations(highways, state_codes)
    candidates = trim_by_price(candidates, C.PRICE_TRIM_FACTOR)
    sort_candidates_by_price(candidates)

    if not candidates:
        raise RoutePlanError("No candidate stations found along the route.")

    # ---- Walk the route locally. No further OSRM calls. ----
    stops           = []
    km_at_last_stop = 0.0

    for _ in range(C.MAX_SEGMENTS):
        km_remaining = total_km - km_at_last_stop
        if km_remaining <= C.MAX_RANGE_KM:
            break

        reachable_from_last = C.MAX_RANGE_KM * C.SAFETY_MARGIN
        target_cum_km = min(km_at_last_stop + reachable_from_last, total_km)

        chosen_station = chosen_dist_km = None
        chosen_cum_km  = None

        d = target_cum_km
        while d > km_at_last_stop and chosen_station is None:
            pt = find_point_at_distance(coords, cum, d)
            st, dist_km = _find_with_widening(pt, candidates)
            if st is not None:
                chosen_station = st
                chosen_dist_km = dist_km
                chosen_cum_km  = d
            d -= C.SAMPLE_STEP_KM

        if chosen_station is None:
            raise RoutePlanError(
                f"No reachable fuel station found along the route between "
                f"km {km_at_last_stop:.0f} and km {target_cum_km:.0f}."
            )

        stops.append({
            "station":       chosen_station,
            "km_from_start": chosen_cum_km,
            "detour_km":     chosen_dist_km,
        })
        km_at_last_stop = chosen_cum_km
    else:
        raise RoutePlanError("Route planning exceeded the segment limit.")

    # ---- Cost model ----
    total_cost = 0.0
    prev_km    = 0.0
    prev_price = None
    for s in stops:
        leg_km  = s["km_from_start"] - prev_km
        leg_gal = (leg_km / C.MILES_TO_KM) / C.MPG
        if prev_price is None:
            prev_price = float(s["station"].price)
        total_cost += leg_gal * prev_price
        prev_km    = s["km_from_start"]
        prev_price = float(s["station"].price)

    final_leg_km  = total_km - prev_km
    final_leg_gal = (final_leg_km / C.MILES_TO_KM) / C.MPG
    if prev_price is not None:
        total_cost += final_leg_gal * prev_price

    # ---- Response ----
    return {
        "start":  {"query": start_query,  "lat": start[0],  "lon": start[1]},
        "finish": {"query": finish_query, "lat": finish[0], "lon": finish[1]},
        "route":  [[c[0], c[1]] for c in coords],
        "stops": [
            {
                "opis_id":       s["station"].opis_id,
                "name":          s["station"].name,
                "city":          s["station"].city,
                "state":         s["station"].state,
                "price":         float(s["station"].price),
                "lat":           s["station"].latitude,
                "lon":           s["station"].longitude,
                "km_from_start": round(s["km_from_start"], 2),
                "mi_from_start": round(s["km_from_start"] / C.MILES_TO_KM, 2),
                "detour_km":     round(s["detour_km"], 2),
                "detour_mi":     round(s["detour_km"] / C.MILES_TO_KM, 2),
            }
            for s in stops
        ],
        "total_km":    round(total_km, 2),
        "total_miles": round(total_km / C.MILES_TO_KM, 2),
        "total_cost":  round(total_cost, 2),
        "assumptions": {
            "start_tank_full":        True,
            "vehicle_range_miles":    C.MAX_RANGE_MILES,
            "efficiency_mpg":         C.MPG,
            "safety_margin":          C.SAFETY_MARGIN,
            "first_leg_price_source": "next_stop",
        },
    }
