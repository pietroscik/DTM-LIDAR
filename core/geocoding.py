import logging

try:
    from geopy.geocoders import Nominatim  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    Nominatim = None


logger = logging.getLogger(__name__)


def geocode_address_to_coords(
    address: str,
    user_agent: str = "flood_risk_prototype",
) -> str:
    """
    Geocode a free-text address into a 'lon,lat' string.

    This uses OpenStreetMap Nominatim via geopy. It requires an active
    internet connection and the `geopy` package installed in the
    Python environment.
    """
    if Nominatim is None:
        raise RuntimeError(
            "geopy is not available. Install it with `pip install geopy` "
            "to enable address geocoding."
        )

    geolocator = Nominatim(user_agent=user_agent)

    # Try a couple of variants to make Nominatim happier
    queries = [address]
    simplified = address.replace("Italia", "").replace("IT", "").strip()
    if simplified and simplified not in queries:
        queries.append(simplified)

    for query in queries:
        location = geolocator.geocode(query, country_codes="it")
        if location is not None:
            lon = float(location.longitude)
            lat = float(location.latitude)
            coords = f"{lon:.6f},{lat:.6f}"
            logger.info("Geocoded address %r to coords %s", address, coords)
            return coords

    raise ValueError(f"Unable to geocode address with Nominatim: {address!r}")

