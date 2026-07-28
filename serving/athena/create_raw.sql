CREATE EXTERNAL TABLE IF NOT EXISTS weatheranalytics.weather_raw (
    city_name STRING,
    latitude DOUBLE,
    longitude DOUBLE,
    temperature_2m DOUBLE,
    wind_speed_10m DOUBLE,
    relative_humidity_2m DOUBLE,
    timestamp STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://weather-anomaly-ca-2026/raw/';