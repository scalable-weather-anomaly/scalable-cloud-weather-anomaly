import numpy as np
import pandas as pd
import json

df = pd.read_parquet("s3://weather-anomaly-ca-2026/baselines/")

with open('/home/ec2-user/environment/weather-anomaly/data/cities/cities_resolved.json') as f:
    cities = json.load(f)
names = [c['name'] for c in cities]
coords = np.array([[c['latitude'], c['longitude']] for c in cities])

def nearest_distance(lat, lon):
    distances = np.sqrt((coords[:, 0] - lat)**2 + (coords[:, 1] - lon)**2)
    idx = distances.argmin()
    return names[idx], distances[idx]

unique_coords = df[['latitude', 'longitude']].drop_duplicates()
results = unique_coords.apply(lambda r: nearest_distance(r['latitude'], r['longitude']), axis=1)
unique_coords['nearest_city'] = results.apply(lambda x: x[0])
unique_coords['distance'] = results.apply(lambda x: x[1])

print(unique_coords.sort_values('distance', ascending=False).head(20))
print(f"\nTotal unique coordinate pairs: {len(unique_coords)}")
print(f"Pairs beyond 0.5 threshold: {(unique_coords['distance'] > 0.5).sum()}")