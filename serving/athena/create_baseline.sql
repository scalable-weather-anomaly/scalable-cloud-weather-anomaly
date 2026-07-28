CREATE EXTERNAL TABLE weatheranalytics.weather_baselines (
    city_name STRING,
    hour_of_day INT,
    temp_mean DOUBLE,
    temp_std DOUBLE,
    wind_mean DOUBLE,
    wind_std DOUBLE
)
STORED AS PARQUET
LOCATION 's3://weather-anomaly-ca-2026/baselines/';