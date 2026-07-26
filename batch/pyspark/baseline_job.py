import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    hour, mean, stddev, col, to_timestamp,
    explode, arrays_zip, input_file_name, regexp_extract
)

S3_BUCKET = sys.argv[1] if len(sys.argv) > 1 else "weather-anomaly-ca-2026"

spark = SparkSession.builder \
    .appName("WeatherAnomalyBaseline") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

input_path  = f"s3://{S3_BUCKET}/historical/"
output_path = f"s3://{S3_BUCKET}/baselines/"

print(f"Reading from : {input_path}")
print(f"Writing to   : {output_path}")

raw = spark.read \
    .option("multiline", "true") \
    .option("recursiveFileLookup", "true") \
    .json(input_path)

raw = raw.withColumn("source_file", input_file_name())
raw = raw.withColumn(
    "city_name",
    regexp_extract(col("source_file"), r"/([^/]+)_\d{4}\.json$", 1)
)

exploded = raw.select(
    col("city_name"),
    explode(
        arrays_zip(
            col("hourly.time").alias("times"),
            col("hourly.temperature_2m").alias("temps"),
            col("hourly.wind_speed_10m").alias("winds"),
            col("hourly.relative_humidity_2m").alias("humidity"),
            col("hourly.precipitation").alias("precipitation")
        )
    ).alias("data")
).select(
    col("city_name"),
    col("data.times").alias("timestamp"),
    col("data.temps").alias("temperature_2m"),
    col("data.winds").alias("wind_speed_10m"),
    col("data.humidity").alias("relative_humidity_2m"),
    col("data.precipitation").alias("precipitation")
)

exploded = exploded.withColumn(
    "hour_of_day", hour(to_timestamp(col("timestamp")))
).filter(col("city_name") != "")

baseline = exploded.groupBy("city_name", "hour_of_day") \
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
baseline.show(5)
spark.stop()
