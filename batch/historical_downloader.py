import sys
import os
import json
import time
import boto3
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from utils.geocoder import load_cities

s3 = boto3.client("s3", region_name=AWS_REGION)

DATE_CHUNKS = [
    ("2020-01-01", "2020-12-31"),
    ("2021-01-01", "2021-12-31"),
    ("2022-01-01", "2022-12-31"),
    ("2023-01-01", "2023-12-31"),
    ("2024-01-01", "2024-12-31"),
    ("2025-01-01", "2025-12-31"),
]

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "pressure_msl",
    "surface_pressure",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "et0_fao_evapotranspiration",
    "vapour_pressure_deficit",
    "soil_temperature_0_to_7cm",
    "soil_moisture_0_to_7cm",
    "uv_index",
    "sunshine_duration",
    "shortwave_radiation",
    "direct_radiation"
]

TARGET_MB  = 1100
BATCH_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 40


def s3_key(city_name, year):
    return f"{S3_HISTORICAL_PREFIX}/{city_name.replace(' ', '_')}_{year}.json"


def already_downloaded(city_name, year):
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=s3_key(city_name, year))
        return True
    except:
        return False


def s3_total_size_mb():
    paginator = s3.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_HISTORICAL_PREFIX):
        for obj in page.get("Contents", []):
            total += obj["Size"]
    return total / 1024 / 1024


def fetch_chunk(city, start, end):
    params = {
        "latitude":   city["latitude"],
        "longitude":  city["longitude"],
        "start_date": start,
        "end_date":   end,
        "hourly":     ",".join(HOURLY_VARIABLES),
        "timezone":   city["timezone"]
    }
    for attempt in range(4):
        try:
            response = requests.get(OPENMETEO_ARCHIVE_URL, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            if response.status_code == 429:
                wait = 45 * (attempt + 1)
                print(f"      rate limited — waiting {wait}s (retry {attempt+1}/4)")
                time.sleep(wait)
            else:
                raise
    raise Exception("Failed after 4 retries")


def save_chunk(city_name, year, data):
    body = json.dumps(data)
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key(city_name, year),
        Body=body,
        ContentType="application/json"
    )
    return len(body)


def run():
    base_dir    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cities_file = os.path.join(base_dir, "data/cities/cities.json")
    all_cities  = load_cities(cities_file)

    already_done = set()
    for city in all_cities:
        if all(already_downloaded(city["name"], s[:4]) for s, _ in DATE_CHUNKS):
            already_done.add(city["name"])

    remaining = [c for c in all_cities if c["name"] not in already_done]
    batch     = remaining[:BATCH_SIZE]

    current_mb = s3_total_size_mb()
    print(f"Total cities     : {len(all_cities)}")
    print(f"Already complete : {len(already_done)}")
    print(f"Remaining        : {len(remaining)}")
    print(f"This batch       : {len(batch)}")
    print(f"Current S3 size  : {current_mb:.0f} MB")
    print(f"Target           : {TARGET_MB} MB")
    print("-" * 60)

    if current_mb >= TARGET_MB:
        print("Already at target. Nothing to download.")
        return

    success = 0
    failed  = []

    for i, city in enumerate(batch):
        current_mb = s3_total_size_mb()
        if current_mb >= TARGET_MB:
            print(f"\nTarget reached — {current_mb:.0f} MB. Stopping.")
            break

        city_bytes = 0

        for start, end in DATE_CHUNKS:
            year = start[:4]
            if already_downloaded(city["name"], year):
                continue
            try:
                data       = fetch_chunk(city, start, end)
                size       = save_chunk(city["name"], year, data)
                city_bytes += size
                success    += 1
                time.sleep(8)
            except Exception as e:
                print(f"      failed {city['name']} {year}: {e}")
                failed.append(f"{city['name']}_{year}")
                time.sleep(15)

        current_mb = s3_total_size_mb()
        print(f"  [{i+1}/{len(batch)}] {city['name']:20s} "
              f"+{city_bytes/1024/1024:.1f}MB  "
              f"S3: {current_mb:.0f}MB / {TARGET_MB}MB")

        time.sleep(5)

    final_mb = s3_total_size_mb()
    print(f"\nBatch complete")
    print(f"S3 total  : {final_mb:.0f} MB ({final_mb/1024:.2f} GB)")
    print(f"Downloaded: {success} year-files")
    if failed:
        print(f"Failed    : {', '.join(failed)}")
    print(f"\nRun again to continue next batch:")
    print(f"  python3 batch/historical_downloader.py 40")


if __name__ == "__main__":
    run()
