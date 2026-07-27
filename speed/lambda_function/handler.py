import json
import boto3
import base64
import os
from datetime import datetime, timezone
from decimal import Decimal

dynamodb  = boto3.resource("dynamodb", region_name="us-east-1")
baselines = dynamodb.Table("weather_baselines")
alerts    = dynamodb.Table("weather_alerts")

Z_THRESHOLD = float(os.environ.get("Z_THRESHOLD", "3.0"))


def get_baseline(city_name, hour_of_day):
    response = baselines.get_item(
        Key={
            "city_name":   city_name,
            "hour_of_day": str(hour_of_day)
        }
    )
    return response.get("Item")


def write_alert(city_name, timestamp, z_score, current_temp, baseline_temp):
    alerts.put_item(Item={
        "city_name":     city_name,
        "timestamp":     timestamp,
        "z_score":       Decimal(str(round(z_score, 4))),
        "current_temp":  Decimal(str(current_temp)),
        "baseline_temp": Decimal(str(round(baseline_temp, 2))),
        "alert_type":    "HOT" if z_score > 0 else "COLD",
        "detected_at":   datetime.now(timezone.utc).isoformat()
    })


def process_record(record):
    payload      = json.loads(base64.b64decode(record["kinesis"]["data"]).decode("utf-8"))
    city_name    = payload["city_name"]
    current_temp = payload["temperature_2m"]
    timestamp    = payload["timestamp"]
    hour_of_day  = str(int(timestamp[11:13])) if len(timestamp) >= 13 else "0"

    baseline = get_baseline(city_name, hour_of_day)
    if not baseline:
        print(f"  No baseline for {city_name} hour {hour_of_day}")
        return

    temp_mean = float(baseline["temp_mean"])
    temp_std  = float(baseline["temp_std"])

    if temp_std == 0:
        return

    z_score = (current_temp - temp_mean) / temp_std
    print(f"  {city_name:15s} temp={current_temp}C  mean={temp_mean:.1f}  z={z_score:.2f}")

    if abs(z_score) > Z_THRESHOLD:
        write_alert(city_name, timestamp, z_score, current_temp, temp_mean)
        print(f"  ALERT written — {city_name} z={z_score:.2f}")


def lambda_handler(event, context):
    records = event.get("Records", [])
    print(f"Processing {len(records)} records")
    for record in records:
        try:
            process_record(record)
        except Exception as e:
            print(f"  Error: {e}")
    return {"statusCode": 200, "body": f"Processed {len(records)} records"}
