import requests
import json
import os
import time

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data/cities/cities_resolved.json")


def resolve_city(name):
    response = requests.get(
        GEOCODING_URL,
        params={"name": name, "count": 1, "language": "en", "format": "json"},
        timeout=10
    )
    response.raise_for_status()
    data = response.json()

    if "results" not in data or len(data["results"]) == 0:
        print(f"  No result found for: {name}")
        return None

    r = data["results"][0]
    return {
        "latitude":  r["latitude"],
        "longitude": r["longitude"],
        "country":   r.get("country", "")
    }


def load_cities(cities_file):
    if os.path.exists(CACHE_PATH):
        print(f"Loading from cache: {CACHE_PATH}")
        with open(CACHE_PATH) as f:
            return json.load(f)

    with open(cities_file) as f:
        cities = json.load(f)

    print(f"Resolving {len(cities)} cities...")
    resolved = []

    for i, city in enumerate(cities):
        print(f"  [{i+1}/{len(cities)}] {city['name']}")
        geo = resolve_city(city["name"])
        if geo:
            resolved.append({
                "name":      city["name"],
                "latitude":  geo["latitude"],
                "longitude": geo["longitude"],
                "timezone":  city["tz"],
                "continent": city["continent"],
                "country":   geo["country"]
            })
        time.sleep(0.3)

    with open(CACHE_PATH, "w") as f:
        json.dump(resolved, f, indent=2)

    print(f"\nDone — {len(resolved)}/{len(cities)} cities resolved and cached")
    return resolved


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cities_file = os.path.join(base_dir, "../data/cities/cities.json")
    cities = load_cities(cities_file)

    print("\nSample:")
    for c in cities[:3]:
        print(f"  {c['name']:15s}  lat={c['latitude']:.4f}  lon={c['longitude']:.4f}  country={c['country']}")
