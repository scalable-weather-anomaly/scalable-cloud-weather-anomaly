import sys
from collections import defaultdict

data = defaultdict(list)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    parts = line.split("\t")
    if len(parts) != 4:
        continue
    city, hour, temp, wind = parts
    try:
        data[(city, hour)].append((float(temp), float(wind)))
    except:
        continue

for (city, hour), values in sorted(data.items()):
    temps = [v[0] for v in values]
    winds = [v[1] for v in values]
    n         = len(temps)
    temp_mean = sum(temps) / n
    wind_mean = sum(winds) / n
    temp_std  = (sum((t - temp_mean) ** 2 for t in temps) / n) ** 0.5
    wind_std  = (sum((w - wind_mean) ** 2 for w in winds) / n) ** 0.5
    print(f"{city}\t{hour}\t{temp_mean:.4f}\t{temp_std:.4f}\t{wind_mean:.4f}\t{wind_std:.4f}")
