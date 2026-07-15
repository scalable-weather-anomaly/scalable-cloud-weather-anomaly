import pandas as pd
import matplotlib.pyplot as plt
import os

CSV_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results/batch_benchmark.csv")
GRAPH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graphs/speedup_graph.png")

df = pd.read_csv(CSV_PATH).sort_values("nodes")
baseline = df[df["nodes"] == 1]["seconds"].values[0]
df["speedup"] = baseline / df["seconds"]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

ax1.plot(df["nodes"], df["seconds"], marker="o", color="steelblue", linewidth=2)
ax1.set_xlabel("Number of EMR Core Nodes")
ax1.set_ylabel("Execution Time (seconds)")
ax1.set_title("Batch Job Execution Time vs Node Count")
ax1.set_xticks(df["nodes"])
ax1.grid(True, alpha=0.3)

for _, row in df.iterrows():
    ax1.annotate(f"{int(row['seconds'])}s",
                 (row["nodes"], row["seconds"]),
                 textcoords="offset points", xytext=(0, 10), ha="center")

ax2.plot(df["nodes"], df["speedup"], marker="o", color="steelblue",
         linewidth=2, label="Actual speedup")
ax2.plot(df["nodes"], df["nodes"],   marker="",  color="gray",
         linewidth=1, linestyle="--", label="Ideal speedup")
ax2.set_xlabel("Number of EMR Core Nodes")
ax2.set_ylabel("Speedup vs 1 Node")
ax2.set_title("Speedup Graph — PySpark Baseline Job")
ax2.set_xticks(df["nodes"])
ax2.legend()
ax2.grid(True, alpha=0.3)

for _, row in df.iterrows():
    ax2.annotate(f"{row['speedup']:.2f}x",
                 (row["nodes"], row["speedup"]),
                 textcoords="offset points", xytext=(0, 10), ha="center")

plt.tight_layout()
os.makedirs(os.path.dirname(GRAPH_PATH), exist_ok=True)
plt.savefig(GRAPH_PATH, dpi=150, bbox_inches="tight")
print(f"Graph saved to {GRAPH_PATH}")
