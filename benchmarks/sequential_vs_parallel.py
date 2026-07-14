import time
import requests
import json
import multiprocessing
import matplotlib.pyplot as plt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.geocoder import load_cities

base_dir    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cities_file = os.path.join(base_dir, "data/cities/cities.json")
all_cities  = load_cities(cities_file)

VARIABLES = "temperature_2m,wind_speed_10m,precipitation,weather_code,relative_humidity_2m"


def fetch_city(city):
    params = {
        "latitude":  city["latitude"],
        "longitude": city["longitude"],
        "current":   VARIABLES,
        "timezone":  city["timezone"],
        "past_days": 1
    }
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
    return r.json()


def run_sequential(cities):
    results = []
    for city in cities:
        results.append(fetch_city(city))
    return results


def run_parallel(cities):
    with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
        results = pool.map(fetch_city, cities)
    return results


def benchmark():
    sizes   = [5, 10, 20, 38]
    seq_times = []
    par_times = []

    print(f"CPU cores available: {multiprocessing.cpu_count()}")
    print("-" * 50)

    for n in sizes:
        cities = all_cities[:n]

        print(f"Testing {n} cities — sequential...")
        t = time.time()
        run_sequential(cities)
        seq_time = round(time.time() - t, 2)
        seq_times.append(seq_time)
        print(f"  Sequential: {seq_time}s")

        time.sleep(5)

        print(f"Testing {n} cities — parallel...")
        t = time.time()
        run_parallel(cities)
        par_time = round(time.time() - t, 2)
        par_times.append(par_time)
        print(f"  Parallel:   {par_time}s")
        print(f"  Speedup:    {round(seq_time/par_time, 2)}x")
        print()

        time.sleep(5)

    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "graphs"), exist_ok=True)

    import csv
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results/seq_vs_parallel.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cities", "sequential_s", "parallel_s", "speedup"])
        writer.writeheader()
        for i, n in enumerate(sizes):
            writer.writerow({
                "cities":       n,
                "sequential_s": seq_times[i],
                "parallel_s":   par_times[i],
                "speedup":      round(seq_times[i] / par_times[i], 2)
            })

    plt.figure(figsize=(10, 5))
    plt.plot(sizes, seq_times, marker="o", color="red",      label="Sequential", linewidth=2)
    plt.plot(sizes, par_times, marker="o", color="steelblue",label="Parallel",   linewidth=2)
    plt.xlabel("Number of Cities Polled")
    plt.ylabel("Time (seconds)")
    plt.title("Sequential vs Parallel Producer — Weather API Polling")
    plt.legend()
    plt.grid(True, alpha=0.3)
    graph_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graphs/sequential_vs_parallel.png")
    plt.savefig(graph_path, dpi=150, bbox_inches="tight")
    print(f"Graph saved to {graph_path}")
    plt.show()


if __name__ == "__main__":
    benchmark()
