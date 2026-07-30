import boto3
import json
import requests
import time
from datetime import datetime, timezone, timedelta

CITIES = [
    {"name": "Dublin",       "lat": 53.33,  "lon": -6.25,   "tz": "Europe/Dublin",       "country": "Ireland",   "continent": "Europe"},
    {"name": "London",       "lat": 51.51,  "lon": -0.13,   "tz": "Europe/London",       "country": "UK",        "continent": "Europe"},
    {"name": "Paris",        "lat": 48.85,  "lon": 2.35,    "tz": "Europe/Paris",        "country": "France",    "continent": "Europe"},
    {"name": "Berlin",       "lat": 52.52,  "lon": 13.40,   "tz": "Europe/Berlin",       "country": "Germany",   "continent": "Europe"},
    {"name": "Madrid",       "lat": 40.42,  "lon": -3.70,   "tz": "Europe/Madrid",       "country": "Spain",     "continent": "Europe"},
    {"name": "Rome",         "lat": 41.90,  "lon": 12.50,   "tz": "Europe/Rome",         "country": "Italy",     "continent": "Europe"},
    {"name": "Moscow",       "lat": 55.75,  "lon": 37.62,   "tz": "Europe/Moscow",       "country": "Russia",    "continent": "Europe"},
    {"name": "Istanbul",     "lat": 41.01,  "lon": 28.95,   "tz": "Europe/Istanbul",     "country": "Turkey",    "continent": "Europe"},
    {"name": "Tokyo",        "lat": 35.68,  "lon": 139.69,  "tz": "Asia/Tokyo",          "country": "Japan",     "continent": "Asia"},
    {"name": "Mumbai",       "lat": 19.07,  "lon": 72.87,   "tz": "Asia/Kolkata",        "country": "India",     "continent": "Asia"},
    {"name": "Dubai",        "lat": 25.20,  "lon": 55.27,   "tz": "Asia/Dubai",          "country": "UAE",       "continent": "Asia"},
    {"name": "Singapore",    "lat": 1.35,   "lon": 103.82,  "tz": "Asia/Singapore",      "country": "Singapore", "continent": "Asia"},
    {"name": "Bangkok",      "lat": 13.75,  "lon": 100.52,  "tz": "Asia/Bangkok",        "country": "Thailand",  "continent": "Asia"},
    {"name": "Seoul",        "lat": 37.57,  "lon": 126.98,  "tz": "Asia/Seoul",          "country": "Korea",     "continent": "Asia"},
    {"name": "Cairo",        "lat": 30.06,  "lon": 31.25,   "tz": "Africa/Cairo",        "country": "Egypt",     "continent": "Africa"},
    {"name": "Lagos",        "lat": 6.45,   "lon": 3.40,    "tz": "Africa/Lagos",        "country": "Nigeria",   "continent": "Africa"},
    {"name": "Nairobi",      "lat": -1.29,  "lon": 36.82,   "tz": "Africa/Nairobi",      "country": "Kenya",     "continent": "Africa"},
    {"name": "Johannesburg", "lat": -26.20, "lon": 28.04,   "tz": "Africa/Johannesburg", "country": "S.Africa",  "continent": "Africa"},
    {"name": "New York",     "lat": 40.71,  "lon": -74.01,  "tz": "America/New_York",    "country": "USA",       "continent": "North America"},
    {"name": "Los Angeles",  "lat": 34.05,  "lon": -118.24, "tz": "America/Los_Angeles", "country": "USA",       "continent": "North America"},
    {"name": "Toronto",      "lat": 43.65,  "lon": -79.38,  "tz": "America/Toronto",     "country": "Canada",    "continent": "North America"},
    {"name": "Mexico City",  "lat": 19.43,  "lon": -99.13,  "tz": "America/Mexico_City", "country": "Mexico",    "continent": "North America"},
    {"name": "Sao Paulo",    "lat": -23.55, "lon": -46.63,  "tz": "America/Sao_Paulo",   "country": "Brazil",    "continent": "South America"},
    {"name": "Buenos Aires", "lat": -34.61, "lon": -58.38,  "tz": "America/Argentina/Buenos_Aires", "country": "Argentina", "continent": "South America"},
    {"name": "Sydney",       "lat": -33.87, "lon": 151.21,  "tz": "Australia/Sydney",    "country": "Australia", "continent": "Oceania"},
    {"name": "Auckland",     "lat": -36.86, "lon": 174.76,  "tz": "Pacific/Auckland",    "country": "NZ",        "continent": "Oceania"},
]


def run():
    session   = boto3.session.Session()
    kinesis   = session.client("kinesis",   region_name="us-east-1")
    dynamodb  = session.resource("dynamodb", region_name="us-east-1")
    baselines = dynamodb.Table("weather_baselines")

    end_date   = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=30)

    print(f"Fetching real weather: {start_date} to {end_date}")
    print(f"Cities: {len(CITIES)}")
    print("-" * 55)

    total = 0

    for city in CITIES:
        try:
            params = {
                "latitude":   city["lat"],
                "longitude":  city["lon"],
                "start_date": str(start_date),
                "end_date":   str(end_date),
                "hourly":     "temperature_2m,wind_speed_10m,precipitation,weather_code,relative_humidity_2m",
                "timezone":   city["tz"]
            }
            resp = requests.get(
                "https://archive-api.open-meteo.com/v1/archive",
                params=params, timeout=30
            )
            resp.raise_for_status()
            data  = resp.json()
            times = data["hourly"]["time"]
            temps = data["hourly"]["temperature_2m"]
            winds = data["hourly"]["wind_speed_10m"]
            precip= data["hourly"]["precipitation"]
            codes = data["hourly"]["weather_code"]
            humid = data["hourly"]["relative_humidity_2m"]

            city_count = 0
            for i, ts in enumerate(times):
                hour = int(ts[11:13])
                temp = temps[i]
                if temp is None:
                    continue
                try:
                    baseline = baselines.get_item(
                        Key={"city_name": city["name"], "hour_of_day": str(hour)}
                    ).get("Item")
                except Exception:
                    continue
                if not baseline:
                    continue
                mean = float(baseline["temp_mean"])
                std  = float(baseline["temp_std"])
                if std == 0:
                    continue
                z = (temp - mean) / std
                if abs(z) > 2.5:
                    record = {
                        "city_name":         city["name"],
                        "country":           city["country"],
                        "continent":         city["continent"],
                        "latitude":          city["lat"],
                        "longitude":         city["lon"],
                        "timestamp":         ts,
                        "temperature_2m":    temp,
                        "wind_speed_10m":    winds[i] or 0.0,
                        "precipitation":     precip[i] or 0.0,
                        "weather_code":      codes[i] or 0,
                        "relative_humidity": humid[i] or 0,
                        "ingested_at":       datetime.now(timezone.utc).isoformat()
                    }
                    kinesis.put_record(
                        StreamName="weather-stream",
                        Data=json.dumps(record),
                        PartitionKey=city["name"]
                    )
                    city_count += 1
                    total      += 1
                    time.sleep(0.1)

            if city_count > 0:
                print(f"  {city['name']:15s} {city_count} anomalies found and pushed")
            else:
                print(f"  {city['name']:15s} no anomalies in last 30 days")

            time.sleep(3)

        except Exception as e:
            print(f"  {city['name']:15s} error: {e}")

    print(f"\nDone — {total} anomalies pushed to Kinesis")
    print("Wait 5-6 minutes for Lambda then refresh dashboard")


if __name__ == "__main__":
    run()
