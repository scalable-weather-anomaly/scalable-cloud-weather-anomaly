import subprocess
import time
import csv
import os
import boto3

S3_BUCKET  = "weather-anomaly-ca-2026"
CLUSTER_ID = ""
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "results/batch_benchmark.csv")

def run_spark_job(cluster_id):
    start = time.time()
    subprocess.run([
        "aws", "emr", "add-steps",
        "--cluster-id", cluster_id,
        "--steps",
        f"Type=Spark,Name=WeatherBaseline,ActionOnFailure=CONTINUE,"
        f"Args=[s3://{S3_BUCKET}/code/baseline_job.py,{S3_BUCKET}]",
        "--region", "us-east-1"
    ])
    end = time.time()
    return round(end - start, 2)


def record(nodes, time_seconds):
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    file_exists = os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["nodes", "time_seconds", "speedup"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "nodes":        nodes,
            "time_seconds": time_seconds,
            "speedup":      round(time_seconds / time_seconds, 2)
        })
    print(f"Recorded: {nodes} nodes = {time_seconds}s")


if __name__ == "__main__":
    print("Manual benchmark recorder")
    print("Run PySpark job on EMR, then record time here")
    print()
    nodes = int(input("Number of core nodes: "))
    secs  = float(input("Job execution time (seconds): "))
    record(nodes, secs)
    print(f"Saved to {OUTPUT_CSV}")
