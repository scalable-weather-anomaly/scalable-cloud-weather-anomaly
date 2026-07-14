import sys
import json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        record = json.loads(line)
        city      = record.get("city_name", "unknown")
        temp      = record.get("temperature_2m")
        wind      = record.get("wind_speed_10m")
        timestamp = record.get("timestamp", "")
        if temp is not None and wind is not None and len(timestamp) >= 13:
            hour = timestamp[11:13]
            print(f"{city}\t{hour}\t{temp}\t{wind}")
    except:
        continue
