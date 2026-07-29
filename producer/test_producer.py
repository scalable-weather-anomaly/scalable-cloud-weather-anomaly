import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from utils.geocoder import load_cities
from speed.producer.producer import fetch_weather, push_to_kinesis, save_to_s3

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cities_file = os.path.join(base_dir, "data/cities/cities.json")
cities = load_cities(cities_file)

print("Testing with 3 cities\n")

for city in cities[:3]:
    try:
        record = fetch_weather(city)
        push_to_kinesis(record)
        save_to_s3(record)
        print(f"  {city['name']:15s} temp={record['temperature_2m']}C  wind={record['wind_speed_10m']}km/h  humidity={record['relative_humidity']}%")
        print(f"  {json.dumps(record, indent=2)}\n")
    except Exception as e:
        print(f"  ERROR {city['name']}: {e}")
