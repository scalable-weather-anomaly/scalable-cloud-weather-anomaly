import sys
import os
import json
import time
import boto3
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *
from utils.geocoder import load_cities

kinesis = boto3.client("kinesis", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)


def fetch_weather(city):
    params = {
        "latitude":  city["latitude"],
        "longitude": city["longitude"],
        "current":   ",".join(WEATHER_VARIABLES),
        "timezone":  city["timezone"],
        "past_days": PAST_DAYS
    }
    response = requests.get(OPENMETEO_BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    current = data["current"]

    return {
        "city_name":         city["name"],
        "country":           city["country"],
        "continent":         city["continent"],
        "latitude":          city["latitude"],
        "longitude":         city["longitude"],
        "timestamp":         current["time"],
        "temperature_2m":    current["temperature_2m"],
        "wind_speed_10m":    current["wind_speed_10m"],
        "precipitation":     current["precipitation"],
        "weather_code":      current["weather_code"],
        "relative_humidity": current["relative_humidity_2m"],
        "ingested_at":       datetime.now(timezone.utc).isoformat()
    }


def push_to_kinesis(record):
    kinesis.put_record(
        StreamName=KINESIS_STREAM,
        Data=json.dumps(record),
        PartitionKey=record["city_name"]
    )


def save_to_s3(record):
    ts = datetime.now(timezone.utc)
    key = (
        f"{S3_RAW_PREFIX}/"
        f"year={ts.year}/month={ts.month:02d}/"
        f"day={ts.day:02d}/hour={ts.hour:02d}/"
        f"{record['city_name'].replace(' ', '_')}_{ts.strftime('%H%M%S')}.json"
    )
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(record),
        ContentType="application/json"
    )


def run():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cities_file = os.path.join(base_dir, "data/cities/cities.json")
    cities = load_cities(cities_file)

    print(f"Starting producer — {len(cities)} cities")
    print(f"Stream : {KINESIS_STREAM}")
    print(f"Bucket : {S3_BUCKET}")
    print("-" * 50)

    cycle = 0
    while True:
        cycle += 1
        print(f"\n[Cycle {cycle}] {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

        for city in cities:
            try:
                record = fetch_weather(city)
                push_to_kinesis(record)
                save_to_s3(record)
                print(f"  {city['name']:15s} temp={record['temperature_2m']}°C  wind={record['wind_speed_10m']}km/h  humidity={record['relative_humidity']}%")
            except Exception as e:
                print(f"  [ERROR] {city['name']}: {e}")
            time.sleep(CITY_POLL_DELAY)

        print(f"\nCycle {cycle} complete. Waiting {POLL_INTERVAL_SECONDS // 60} minutes...")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
