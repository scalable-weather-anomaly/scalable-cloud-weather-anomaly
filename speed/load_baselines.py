import boto3
import pandas as pd
import numpy as np
import json
from decimal import Decimal
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

S3_BASELINES_PATH = "s3://weather-anomaly-ca-2026/baselines/"
TABLE_NAME = "weather_baselines"
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CITIES_LOOKUP_PATH = os.path.join(BASE_DIR, '..', 'data', 'cities', 'cities_resolved.json')

def load_city_lookup():
    with open(CITIES_LOOKUP_PATH) as f:
        cities = json.load(f)
    names = [c['name'] for c in cities]
    coords = np.array([[c['latitude'], c['longitude']] for c in cities])
    return names, coords


def map_lat_lon_to_city(df, names, coords, max_distance=0.5):
    def find_nearest(lat, lon):
        distances = np.sqrt((coords[:, 0] - lat)**2 + (coords[:, 1] - lon)**2)
        idx = distances.argmin()
        if distances[idx] > max_distance:
            return None
        return names[idx]

    df['city_name'] = df.apply(lambda row: find_nearest(row['latitude'], row['longitude']), axis=1)
    unmatched = df['city_name'].isna().sum()
    if unmatched > 0:
        logger.warning(f"{unmatched} rows could not be matched to a city_name")
    return df.dropna(subset=['city_name'])

def to_decimal(value):
    if value is None or pd.isna(value):
        return Decimal("0")
    return Decimal(str(round(float(value), 6)))


def load_baselines():
    logger.info(f"Reading Parquet from {S3_BASELINES_PATH}")
    df = pd.read_parquet(S3_BASELINES_PATH)
    logger.info(f"Loaded {len(df)} rows. Columns: {list(df.columns)}")

    names, coords = load_city_lookup()
    df = map_lat_lon_to_city(df, names, coords)
    logger.info(f"Mapped to city_name. {len(df)} rows remaining after matching.")

    required_cols = {'city_name', 'hour_of_day', 'temp_mean', 'temp_std', 'wind_mean', 'wind_std'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected columns in Parquet output: {missing}")

    df['hour_of_day'] = df['hour_of_day'].astype(int)
    df['city_name'] = df['city_name'].astype(str)

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(TABLE_NAME)

    written = 0
    with table.batch_writer(overwrite_by_pkeys=['city_name', 'hour_of_day']) as batch:
        for _, row in df.iterrows():
            batch.put_item(Item={
                'city_name': row['city_name'],
                'hour_of_day': str(int(row['hour_of_day'])),
                'temp_mean': to_decimal(row['temp_mean']),
                'temp_std': to_decimal(row['temp_std']),
                'wind_mean': to_decimal(row['wind_mean']),
                'wind_std': to_decimal(row['wind_std']),
            })
            written += 1

    logger.info(f"DONE. {written} baseline rows written to {TABLE_NAME}")


if __name__ == "__main__":
    load_baselines()