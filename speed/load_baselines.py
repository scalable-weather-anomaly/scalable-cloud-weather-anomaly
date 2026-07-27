import boto3
import pandas as pd
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table    = dynamodb.Table("weather_baselines")

BASELINES_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../batch/output/baselines.csv"
)


def load():
    if not os.path.exists(BASELINES_CSV):
        print("baselines.csv not found")
        print("Run: git pull")
        return

    df = pd.read_csv(BASELINES_CSV)
    print(f"Loading {len(df)} records into DynamoDB...")

    success = 0
    with table.batch_writer() as batch:
        for _, row in df.iterrows():
            try:
                batch.put_item(Item={
                    "city_name":   str(row["city_name"]),
                    "hour_of_day": str(int(row["hour_of_day"])),
                    "temp_mean":   Decimal(str(round(float(row["temp_mean"]), 4))),
                    "temp_std":    Decimal(str(round(float(row["temp_std"]),  4))),
                    "wind_mean":   Decimal(str(round(float(row["wind_mean"]), 4))),
                    "wind_std":    Decimal(str(round(float(row["wind_std"]),  4))),
                })
                success += 1
            except Exception as e:
                print(f"  Error row {_}: {e}")

    print(f"Done — {success}/{len(df)} records loaded into weather_baselines")


if __name__ == "__main__":
    load()
