SELECT
    city_name,
    timestamp,
    current_temperature,
    temp_mean,
    temp_std,
    temperature_z_score,
    anomaly_status
FROM weatheranalytics.current_weather_anomalies
ORDER BY abs(temperature_z_score) DESC
LIMIT 20;