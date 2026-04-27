"""Find restaurants within a 5-mile radius of a given address.

Uses OpenStreetMap services (no API key required):
  - Nominatim for geocoding the input address
  - Overpass API for querying nearby restaurants
"""

import argparse
import math
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Eateries/1.0 (restaurant-finder)"
MILES_TO_METERS = 1609.344


def geocode(address: str) -> tuple[float, float, str]:
    """Resolve an address to (latitude, longitude, display_name)."""
    params = urlencode({"q": address, "format": "json", "limit": 1})
    req = Request(f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        results = json.loads(resp.read().decode("utf-8"))
    if not results:
        raise ValueError(f"Could not geocode address: {address!r}")
    r = results[0]
    return float(r["lat"]), float(r["lon"]), r.get("display_name", "")


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in miles."""
    r_miles = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r_miles * math.asin(math.sqrt(a))


def find_restaurants(lat: float, lon: float, radius_miles: float) -> list[dict]:
    """Query Overpass for restaurants within the given radius (miles)."""
    radius_m = int(radius_miles * MILES_TO_METERS)
    query = f"""
    [out:json][timeout:60];
    (
      nwr["amenity"="restaurant"](around:{radius_m},{lat},{lon});
      nwr["amenity"="fast_food"](around:{radius_m},{lat},{lon});
      nwr["amenity"="cafe"](around:{radius_m},{lat},{lon});
      nwr["amenity"="food_court"](around:{radius_m},{lat},{lon});
    );
    out center tags;
    """
    data = urlencode({"data": query}).encode("utf-8")
    req = Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    results = []
    for el in payload.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        if "lat" in el and "lon" in el:
            elat, elon = el["lat"], el["lon"]
        elif "center" in el:
            elat, elon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue

        addr_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:city"),
            tags.get("addr:state"),
            tags.get("addr:postcode"),
        ]
        address = ", ".join(p for p in addr_parts if p)

        results.append({
            "name": name,
            "category": tags.get("amenity", ""),
            "cuisine": tags.get("cuisine", ""),
            "address": address,
            "lat": elat,
            "lon": elon,
            "distance_miles": haversine_miles(lat, lon, elat, elon),
        })

    # De-duplicate: Overpass can return both a node and a way for the same place.
    seen: dict[tuple, dict] = {}
    for r in results:
        key = (r["name"].lower(), round(r["lat"], 4), round(r["lon"], 4))
        if key not in seen or r["distance_miles"] < seen[key]["distance_miles"]:
            seen[key] = r

    return sorted(seen.values(), key=lambda r: r["distance_miles"])


def main() -> int:
    parser = argparse.ArgumentParser(description="List restaurants within a radius of an address.")
    parser.add_argument("address", nargs="?", help="Street address to search around.")
    parser.add_argument("--radius", type=float, default=5.0, help="Search radius in miles (default: 5).")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a table.")
    args = parser.parse_args()

    address = args.address or input("Enter an address: ").strip()
    if not address:
        print("Error: address is required.", file=sys.stderr)
        return 2

    print(f"Geocoding: {address}", file=sys.stderr)
    lat, lon, display = geocode(address)
    print(f"Resolved to: {display}  ({lat:.5f}, {lon:.5f})", file=sys.stderr)

    # Nominatim usage policy asks for <=1 req/sec.
    time.sleep(1)

    print(f"Searching for restaurants within {args.radius} miles...", file=sys.stderr)
    restaurants = find_restaurants(lat, lon, args.radius)
    print(f"Found {len(restaurants)} result(s).\n", file=sys.stderr)

    if args.json:
        print(json.dumps(restaurants, indent=2))
        return 0

    if not restaurants:
        print("No restaurants found.")
        return 0

    print(f"{'#':>3}  {'Dist(mi)':>8}  {'Type':<12}  {'Cuisine':<20}  Name / Address")
    print("-" * 100)
    for i, r in enumerate(restaurants, 1):
        print(f"{i:>3}  {r['distance_miles']:>8.2f}  {r['category']:<12}  {r['cuisine'][:20]:<20}  {r['name']}")
        if r["address"]:
            print(f"{'':>3}  {'':>8}  {'':<12}  {'':<20}  {r['address']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)