import json
import base64
import boto3
import logging
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
BASELINES_TABLE = dynamodb.Table('weather_baselines')
ALERTS_TABLE = dynamodb.Table('weather_alerts')

Z_SCORE_THRESHOLD = 3.0


def get_baseline(city_name, hour_of_day):
    #Fetch mean/stddev for a city + hour from DynamoDB weather_baselines.
    try:
        response = BASELINES_TABLE.get_item(
            Key={
                'city_name': city_name,
                'hour_of_day': hour_of_day
            }
        )
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error fetching baseline for {city_name} hour {hour_of_day}: {e}")
        return None


def calculate_z_score(current_value, mean, stddev):
    #z = (current - mean) / stddev. Returns None if stddev is 0 or invalid.
    try:
        mean = float(mean)
        stddev = float(stddev)
        if stddev == 0:
            return None
        return (float(current_value) - mean) / stddev
    except (TypeError, ValueError):
        return None


def write_alert(city_name, timestamp, z_score, current_temp, metric='temperature_2m'):
    #Write an anomaly alert to DynamoDB weather_alerts.
    try:
        ALERTS_TABLE.put_item(
            Item={
                'city_name': city_name,
                'timestamp': timestamp,
                'z_score': Decimal(str(round(z_score, 4))),
                'current_temp': Decimal(str(current_temp)),
                'metric': metric,
                'detected_at': datetime.now(timezone.utc).isoformat()
            }
        )
        logger.info(f"ALERT written: {city_name} | z={round(z_score, 2)} | temp={current_temp}")
    except Exception as e:
        logger.error(f"Failed to write alert for {city_name}: {e}")


def process_record(record_data):
    #Process a single decoded weather record from Kinesis.
    try:
        city_name = record_data['city_name']
        current_temp = record_data['temperature_2m']
        timestamp = record_data.get('timestamp') or record_data.get('ingested_at')

        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00')) if 'Z' in timestamp else datetime.fromisoformat(timestamp)
        hour_of_day = ts.hour

        baseline = get_baseline(city_name, hour_of_day)

        if not baseline:
            logger.info(f"No baseline found for {city_name} hour {hour_of_day} — skipping (batch layer may not have run yet)")
            return

        temp_mean = baseline.get('temp_mean')
        temp_std = baseline.get('temp_std')

        z = calculate_z_score(current_temp, temp_mean, temp_std)

        logger.info(f"Processed {city_name} | hour={hour_of_day} | temp={current_temp} | z={z}")

        if z is not None and abs(z) > Z_SCORE_THRESHOLD:
            write_alert(city_name, timestamp, z, current_temp)

    except KeyError as e:
        logger.error(f"Missing expected field in record: {e} | record: {record_data}")
    except Exception as e:
        logger.error(f"Unexpected error processing record: {e} | record: {record_data}")


def lambda_handler(event, context):

    #Entry point. Triggered by Kinesis with batch_size=100, batch_window=300s (the 5-minute sliding window).
    records = event.get('Records', [])
    logger.info(f"Received {len(records)} records from Kinesis")

    processed_count = 0
    alert_count = 0

    for record in records:
        try:
            payload = base64.b64decode(record['kinesis']['data'])
            record_data = json.loads(payload)
            process_record(record_data)
            processed_count += 1
        except Exception as e:
            logger.error(f"Failed to decode/process Kinesis record: {e}")

    logger.info(f"Batch complete: {processed_count}/{len(records)} records processed")

    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': processed_count,
            'total': len(records)
        })
    }