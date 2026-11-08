import re
import unicodedata

from haversine import haversine
import googlemaps

from config import settings
from helpers.server_message import ServerMessageException

gmaps = None

# Google Places types queried for each category the API exposes. Clinic also
# queries "hospital": around Lomé that type is where the neighbourhood CMS and
# cliniques are filed, while "doctor" alone is dominated by specialists.
PLACE_TYPES_BY_CATEGORY = {
    "pharmacy": ("pharmacy",),
    "hospital": ("hospital",),
    "clinic": ("doctor", "hospital"),
}

# Google's own classification cannot be trusted here. Asked for the nearest
# "doctor" in Lomé it ranks first an economic investigation firm, then a
# veterinarian, an optician and a ministry building, all typed doctor/health.
# None of these answers someone looking for a pharmacy, hospital or clinic.
_EXCLUDED_TYPES = frozenset({"veterinary_care"})
_EXCLUDED_NAME = re.compile(
    r"veterinaire|\bveto\b|optique|opticien|lunette|basse vision"
    r"|investigation|economique|ministere|avocat|notaire|assurance|banque|immobili"
)

# Names that look like what the category is for. Such a place is preferred over
# a closer one that merely carries the Google type: a general clinic or a
# gynaecologist over an ophthalmology practice for someone asking for a clinic.
_PREFERRED_NAME = {
    "pharmacy": re.compile(r"pharma"),
    # "\bclinic" also covers "Clinical": English names such as Clinical Kômombo
    # or Clinical Bayal are common for local clinics in Lomé.
    "hospital": re.compile(r"hopital|\bchu\b|\bchr\b|centre hospitalier|clinique|\bclinic|\bcms\b"),
    "clinic": re.compile(
        r"clinique|\bclinic|\bcms\b|centre (medico|de sante|medical)|dispensaire"
        r"|cabinet medical|maternite|gyneco|hopital|\busp\b|\bcsps\b"
    ),
}


def _fold(text: str) -> str:
    """Lowercases and strips accents, so "Hôpital" matches "hopital"."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def select_closest_place(category: str, candidates: list, user_location: tuple, radius_km: float):
    """Chooses which Google Places result to recommend, or None.

    Drops closed places, non-health businesses Google mislabels and anything
    outside the radius, then prefers a place whose name matches the category
    and breaks ties by distance. Returns (place, distance_km). Kept free of
    network calls so the selection rules can be tested directly.
    """
    preferred = _PREFERRED_NAME.get(category)
    best = None
    best_key = None
    seen = set()
    for place in candidates:
        identity = place.get("place_id") or place.get("name")
        if identity in seen:
            continue
        seen.add(identity)

        if place.get("business_status", "OPERATIONAL") != "OPERATIONAL":
            continue
        if _EXCLUDED_TYPES.intersection(place.get("types", [])):
            continue
        folded = _fold(place.get("name", ""))
        if _EXCLUDED_NAME.search(folded):
            continue
        location = (place.get("geometry") or {}).get("location")
        if not location:
            continue

        distance = haversine(user_location, (location["lat"], location["lng"]))
        if distance > radius_km:
            continue

        key = (0 if preferred and preferred.search(folded) else 1, distance)
        if best_key is None or key < best_key:
            best, best_key = (place, distance), key
    return best


def _get_gmaps_client():
    global gmaps
    if gmaps is None:
        if not settings.GOOGLE_API_KEY:
            raise ServerMessageException("SERVER_ERROR", meta={"detail": "GOOGLE_API_KEY not configured"})
        gmaps = googlemaps.Client(key=settings.GOOGLE_API_KEY)
    return gmaps


def get_closest_place(category: str, lat: float, lon: float, radius_km: float = 10):
    """Finds the place to recommend for a category, within radius_km.

    The previous version returned Google's first result as-is, so whatever
    Google ranked nearest was sent to the user, mislabelled or not, and the
    radius the caller asked for was ignored entirely.
    """
    candidates = []
    try:
        client = _get_gmaps_client()
        for place_type in PLACE_TYPES_BY_CATEGORY[category]:
            response = client.places_nearby(
                location=(lat, lon),
                rank_by="distance",
                type=place_type,
            )
            candidates.extend(response.get("results", []))
    except ServerMessageException:
        raise
    except Exception:
        raise ServerMessageException("GOOGLE_MAPS_API_ERROR")

    selected = select_closest_place(category, candidates, (lat, lon), radius_km)
    if selected is None:
        return None

    place, distance = selected
    name = place.get("name", "Unknown")
    location = place["geometry"]["location"]
    distance_km = round(distance, 2)
    maps_url = f"https://maps.google.com/?q={location['lat']},{location['lng']}"

    return {
        "name": name,
        "latitude": location["lat"],
        "longitude": location["lng"],
        "distance_km": distance_km,
        "google_maps_url": maps_url
    }


def geocode_place(query: str):
    """Resolves a free-form place name into coordinates via the Google Geocoding API."""
    try:
        client = _get_gmaps_client()
        results = client.geocode(query)
    except ServerMessageException:
        raise
    except Exception:
        raise ServerMessageException("GOOGLE_MAPS_API_ERROR")

    if not results:
        return None

    top = results[0]
    location = top["geometry"]["location"]
    return {
        "query": query,
        "address": top.get("formatted_address", query),
        "latitude": location["lat"],
        "longitude": location["lng"],
        "place_id": top.get("place_id"),
        "google_maps_url": f"https://maps.google.com/?q={location['lat']},{location['lng']}",
    }
