import boto3
import pandas as pd
from decimal import Decimal
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

S3_BASELINES_PATH = "s3://weather-anomaly-ca-2026/baselines/"
TABLE_NAME = "weather_baselines"


def to_decimal(value):
    if value is None or pd.isna(value):
        return Decimal("0")
    return Decimal(str(round(float(value), 6)))


def load_baselines():
    logger.info(f"Reading Parquet from {S3_BASELINES_PATH}")
    df = pd.read_parquet(S3_BASELINES_PATH)
    logger.info(f"Loaded {len(df)} rows. Columns: {list(df.columns)}")

    required_cols = {'city_name', 'hour_of_day', 'temp_mean', 'temp_std', 'wind_mean', 'wind_std'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected columns in Parquet output: {missing}")

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(TABLE_NAME)

    written = 0
    with table.batch_writer(overwrite_by_pkeys=['city_name', 'hour_of_day']) as batch:
        for _, row in df.iterrows():
            batch.put_item(Item={
                'city_name': str(row['city_name']),
                'hour_of_day': int(row['hour_of_day']),
                'temp_mean': to_decimal(row['temp_mean']),
                'temp_std': to_decimal(row['temp_std']),
                'wind_mean': to_decimal(row['wind_mean']),
                'wind_std': to_decimal(row['wind_std']),
            })
            written += 1

    logger.info(f"DONE. {written} baseline rows written to {TABLE_NAME}")


if __name__ == "__main__":
    load_baselines()