CREATE OR REPLACE VIEW weatheranalytics.current_weather_anomalies AS
SELECT
    r.city_name,
    r.latitude,
    r.longitude,
    r.timestamp,
    r.temperature_2m AS current_temperature,
    r.wind_speed_10m AS current_wind_speed,
    b.hour_of_day,
    b.temp_mean,
    b.temp_std,
    b.wind_mean,
    b.wind_std,
    CASE
        WHEN b.temp_std > 0
        THEN (r.temperature_2m - b.temp_mean) / b.temp_std
        ELSE NULL
    END AS temperature_z_score,
    CASE
        WHEN b.wind_std > 0
        THEN (r.wind_speed_10m - b.wind_mean) / b.wind_std
        ELSE NULL
    END AS wind_z_score,
    CASE
        WHEN b.temp_std > 0
             AND abs((r.temperature_2m - b.temp_mean) / b.temp_std) >= 3
        THEN 'TEMPERATURE_ANOMALY'
        WHEN b.wind_std > 0
             AND abs((r.wind_speed_10m - b.wind_mean) / b.wind_std) >= 3
        THEN 'WIND_ANOMALY'
        ELSE 'NORMAL'
    END AS anomaly_status
FROM weatheranalytics.weather_raw r
LEFT JOIN weatheranalytics.weather_baselines b
    ON r.city_name = b.city_name
    AND hour(date_parse(r.timestamp, '%Y-%m-%dT%H:%i')) = b.hour_of_day;