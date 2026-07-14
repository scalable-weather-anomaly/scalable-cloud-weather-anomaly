import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import hour, mean, stddev, col, to_timestamp

S3_BUCKET = sys.argv[1] if len(sys.argv) > 1 else "weather-anomaly-ca-2026"

spark = SparkSession.builder \
    .appName("WeatherAnomalyBaseline") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

input_path  = f"s3://{S3_BUCKET}/historical/*.json"
output_path = f"s3://{S3_BUCKET}/baselines/"

print(f"Reading from : {input_path}")
print(f"Writing to  : {output_path}")

df = spark.read \
    .option("multiline", "true") \
    .json(input_path)

hourly = df.select(
    col("latitude"),
    col("longitude"),
    col("hourly.time").alias("times"),
    col("hourly.temperature_2m").alias("temps"),
    col("hourly.wind_speed_10m").alias("winds"),
    col("hourly.relative_humidity_2m").alias("humidity"),
    col("hourly.precipitation").alias("precipitation"),
    col("hourly.weather_code").alias("weather_code")
)

from pyspark.sql.functions import arrays_zip, explode

exploded = hourly.select(
    "latitude",
    "longitude",
    explode(
        arrays_zip("times", "temps", "winds", "humidity", "precipitation", "weather_code")
    ).alias("data")
).select(
    "latitude",
    "longitude",
    col("data.times").alias("timestamp"),
    col("data.temps").alias("temperature_2m"),
    col("data.winds").alias("wind_speed_10m"),
    col("data.humidity").alias("relative_humidity_2m"),
    col("data.precipitation").alias("precipitation"),
    col("data.weather_code").alias("weather_code")
)

exploded = exploded.withColumn(
    "hour_of_day", hour(to_timestamp(col("timestamp")))
)

baseline = exploded.groupBy("latitude", "longitude", "hour_of_day") \
    .agg(
        mean("temperature_2m").alias("temp_mean"),
        stddev("temperature_2m").alias("temp_std"),
        mean("wind_speed_10m").alias("wind_mean"),
        stddev("wind_speed_10m").alias("wind_std"),
        mean("relative_humidity_2m").alias("humidity_mean"),
        mean("precipitation").alias("precip_mean")
    )

baseline.write \
    .mode("overwrite") \
    .parquet(output_path)

count = baseline.count()
print(f"Baseline records written: {count}")
spark.stop()
