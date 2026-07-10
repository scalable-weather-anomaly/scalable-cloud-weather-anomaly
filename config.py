AWS_REGION          = "us-east-1"
KINESIS_STREAM      = "weather-stream"
S3_BUCKET           = "weather-anomaly-ca-2026"
DYNAMODB_ALERTS     = "weather_alerts"
DYNAMODB_BASELINES  = "weather_baselines"

S3_RAW_PREFIX        = "raw"
S3_HISTORICAL_PREFIX = "historical"
S3_BASELINES_PREFIX  = "baselines"
S3_SERVING_PREFIX    = "serving"

POLL_INTERVAL_SECONDS = 900
CITY_POLL_DELAY       = 2
PAST_DAYS             = 1

ANOMALY_Z_THRESHOLD   = 3.0

OPENMETEO_BASE_URL    = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

WEATHER_VARIABLES = [
    "temperature_2m",
    "wind_speed_10m",
    "precipitation",
    "weather_code",
    "relative_humidity_2m"
]
