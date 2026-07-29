import boto3
import json
import time
import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

kinesis  = boto3.client("kinesis",   region_name="us-east-1")
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
alerts   = dynamodb.Table("weather_alerts")

OUTPUT_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../../benchmarks/results/latency_benchmark.csv"
)

TEST_CITIES = [
    {"city_name": "Dublin",  "temperature_2m": 45.0, "wind_speed_10m": 30.0,
     "precipitation": 0.0, "weather_code": 0, "relative_humidity": 70,
     "latitude": 53.33, "longitude": -6.25, "country": "Ireland", "continent": "Europe"},
    {"city_name": "London",  "temperature_2m": 48.0, "wind_speed_10m": 25.0,
     "precipitation": 0.0, "weather_code": 0, "relative_humidity": 65,
     "latitude": 51.51, "longitude": -0.13, "country": "UK", "continent": "Europe"},
    {"city_name": "Paris",   "temperature_2m": 50.0, "wind_speed_10m": 20.0,
     "precipitation": 0.0, "weather_code": 0, "relative_humidity": 60,
     "latitude": 48.85, "longitude": 2.35, "country": "France", "continent": "Europe"},
    {"city_name": "Berlin",  "temperature_2m": 46.0, "wind_speed_10m": 18.0,
     "precipitation": 0.0, "weather_code": 0, "relative_humidity": 55,
     "latitude": 52.52, "longitude": 13.40, "country": "Germany", "continent": "Europe"},
    {"city_name": "Madrid",  "temperature_2m": 52.0, "wind_speed_10m": 15.0,
     "precipitation": 0.0, "weather_code": 0, "relative_humidity": 30,
     "latitude": 40.42, "longitude": -3.70, "country": "Spain", "continent": "Europe"},
]

RATES = [
    {"label": "low",    "cities": TEST_CITIES[:1]},
    {"label": "medium", "cities": TEST_CITIES[:3]},
    {"label": "high",   "cities": TEST_CITIES},
]


def push_record(city):
    record = {
        **city,
        "timestamp":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00"),
        "ingested_at": datetime.now(timezone.utc).isoformat()
    }
    t = time.time()
    kinesis.put_record(
        StreamName="weather-stream",
        Data=json.dumps(record),
        PartitionKey=city["city_name"]
    )
    return t, record["city_name"], record["timestamp"]


def wait_for_alert(city_name, timestamp, timeout=400):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = alerts.get_item(Key={"city_name": city_name, "timestamp": timestamp})
        if "Item" in resp:
            return time.time()
        time.sleep(5)
    return None


def run():
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    results = []

    print(f"Latency benchmark starting — {sum(len(r['cities']) for r in RATES)} total pushes")
    print("-" * 55)

    for rate in RATES:
        label  = rate["label"]
        cities = rate["cities"]
        print(f"\nRate: {label} ({len(cities)} records)")

        for city in cities:
            t_push, city_name, timestamp = push_record(city)
            print(f"  {city_name} pushed — waiting...")
            t_recv = wait_for_alert(city_name, timestamp)

            if t_recv:
                latency_ms = round((t_recv - t_push) * 1000, 2)
                print(f"  alert received in {latency_ms}ms")
                results.append({"rate": label, "city": city_name,
                                 "latency_ms": latency_ms, "records": len(cities)})
            else:
                print(f"  no alert within 400s")
                results.append({"rate": label, "city": city_name,
                                 "latency_ms": -1, "records": len(cities)})

        time.sleep(10)

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["rate", "city", "latency_ms", "records"])
        writer.writeheader()
        writer.writerows(results)

    valid = [r for r in results if r["latency_ms"] > 0]
    print(f"\nDone — {len(valid)}/{len(results)} alerts received")
    print(f"Results saved to {OUTPUT_CSV}")
    if valid:
        avg = sum(r["latency_ms"] for r in valid) / len(valid)
        print(f"Average latency: {avg:.0f}ms")


if __name__ == "__main__":
    run()
