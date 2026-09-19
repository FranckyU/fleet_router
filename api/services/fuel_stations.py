import math
from decimal import Decimal

from api.models import FuelStation

STATE_BBOX = {
    "AL": (30.22, 35.01, -88.47, -84.89),
    "AZ": (31.33, 37.00, -114.82, -109.04),
    "AR": (33.00, 36.50, -94.62, -89.64),
    "CA": (32.53, 42.01, -124.41, -114.13),
    "CO": (36.99, 41.00, -109.06, -102.04),
    "CT": (40.98, 42.05, -73.73, -71.79),
    "DE": (38.45, 39.84, -75.79, -75.05),
    "DC": (38.79, 38.99, -77.12, -76.91),
    "FL": (24.40, 31.00, -87.63, -80.03),
    "GA": (30.36, 35.00, -85.61, -80.84),
    "ID": (41.99, 49.00, -117.24, -111.04),
    "IL": (36.97, 42.51, -91.51, -87.02),
    "IN": (37.77, 41.76, -88.10, -84.78),
    "IA": (40.37, 43.50, -96.64, -90.14),
    "KS": (36.99, 40.00, -102.05, -94.59),
    "KY": (36.50, 39.15, -89.57, -81.96),
    "LA": (28.93, 33.02, -94.04, -88.82),
    "ME": (43.06, 47.46, -71.08, -66.95),
    "MD": (37.91, 39.72, -79.49, -75.05),
    "MA": (41.24, 42.89, -73.51, -69.93),
    "MI": (41.70, 48.19, -90.42, -82.42),
    "MN": (43.50, 49.38, -97.24, -89.49),
    "MS": (30.17, 35.00, -91.66, -88.10),
    "MO": (35.99, 40.61, -95.77, -89.10),
    "MT": (44.36, 49.00, -116.05, -104.04),
    "NE": (39.99, 43.00, -104.05, -95.31),
    "NV": (35.00, 42.00, -120.01, -114.04),
    "NH": (42.70, 45.31, -72.56, -70.61),
    "NJ": (38.93, 41.36, -75.56, -73.89),
    "NM": (31.33, 37.00, -109.05, -103.00),
    "NY": (40.50, 45.02, -79.76, -71.86),
    "NC": (33.88, 36.59, -84.32, -75.46),
    "ND": (45.94, 49.00, -104.05, -96.55),
    "OH": (38.40, 42.32, -84.82, -80.52),
    "OK": (33.62, 37.00, -103.00, -94.43),
    "OR": (41.99, 46.29, -124.57, -116.46),
    "PA": (39.72, 42.27, -80.52, -74.69),
    "RI": (41.15, 42.02, -71.86, -71.12),
    "SC": (32.03, 35.22, -83.36, -78.54),
    "SD": (42.48, 45.95, -104.06, -96.44),
    "TN": (34.98, 36.68, -90.31, -81.65),
    "TX": (25.84, 36.50, -106.65, -93.51),
    "UT": (36.99, 42.00, -114.05, -109.04),
    "VT": (42.73, 45.02, -73.44, -71.46),
    "VA": (36.54, 39.47, -83.68, -75.24),
    "WA": (45.54, 49.00, -124.85, -116.92),
    "WV": (37.20, 40.64, -82.64, -77.72),
    "WI": (42.49, 47.08, -92.89, -86.25),
    "WY": (40.99, 45.01, -111.06, -104.05),
}


def haversine_km(a, b):
    R = 6371.0088
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def route_bbox(route_coords):
    lats = [c[0] for c in route_coords]
    lons = [c[1] for c in route_coords]
    return min(lats), max(lats), min(lons), max(lons)


def states_in_bbox(bbox):
    r_minlat, r_maxlat, r_minlon, r_maxlon = bbox
    out = []
    for state, (s_minlat, s_maxlat, s_minlon, s_maxlon) in STATE_BBOX.items():
        if not (s_maxlat < r_minlat or s_minlat > r_maxlat or
                s_maxlon < r_minlon or s_minlon > r_maxlon):
            out.append(state)
    return out


def candidate_stations(highways, state_codes, max_price=None):
    qs = FuelStation.objects.filter(
        state__in=state_codes,
        latitude__isnull=False,
        longitude__isnull=False,
    )
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)

    highways_upper = {h.upper() for h in highways}
    hits = []
    for s in qs.only("id", "opis_id", "name", "address", "city",
                     "state", "price", "latitude", "longitude"):
        if not highways_upper:
            hits.append(s)
            continue
        addr = (s.address or "").upper()
        if any(h in addr for h in highways_upper):
            hits.append(s)
    return hits


def sort_candidates_by_price(candidates):
    """Sort in-place, cheapest first, NULLs last. Returns same list."""
    candidates.sort(key=lambda s: (s.price is None, s.price))
    return candidates


def trim_by_price(candidates, max_multiplier):
    """
    Drop candidates priced > max_multiplier × cheapest candidate.

    `price` is a Decimal from the DB, so the multiplier must also be a
    Decimal (converted via str() to avoid binary-float artifacts).
    """
    priced = [s for s in candidates if s.price is not None]
    if not priced:
        return candidates
    cheapest = min(s.price for s in priced)
    cutoff = cheapest * Decimal(str(max_multiplier))
    return [s for s in candidates if s.price is None or s.price <= cutoff]


def cumulative_km(coords):
    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + haversine_km(coords[i - 1], coords[i]))
    return cum


def find_point_at_distance(coords, cum, target_km):
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < target_km:
            lo = mid + 1
        else:
            hi = mid
    return coords[lo]
