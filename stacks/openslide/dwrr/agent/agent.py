from flask import Flask
import requests
import os
import re

app = Flask(__name__)

# ============================
# CONFIG
# ============================
PROM_URL = os.getenv("PROM_URL", "http://imgbox2:9090")
SERVICE_NAME = os.getenv("SERVICE_NAME", "openslide_iiif-openslide")

CPU_LIMIT = float(os.getenv("CPU_LIMIT", 2.0))          # core limit
MEM_LIMIT = float(os.getenv("MEM_LIMIT", 2 * 1024**3))  # default 2GB
NET_LIMIT = float(os.getenv("NET_LIMIT", 5 * 1024**2))  # default 5MB/s

# ============================
# PROMETHEUS QUERIES
# ============================

QUERY_CPU = f"""
sum by (container_label_com_docker_swarm_task_name) (
  avg_over_time(
    irate(
      container_cpu_usage_seconds_total{{container_label_com_docker_swarm_service_name="{SERVICE_NAME}"}}[1m]
    )[2m:]
  )
)
"""

QUERY_MEM = f"""
sum by (container_label_com_docker_swarm_task_name) (
  container_memory_rss{{container_label_com_docker_swarm_service_name="{SERVICE_NAME}"}}
)
"""

QUERY_NET = f"""
sum by (container_label_com_docker_swarm_task_name) (
  avg_over_time(
    irate(
      container_network_receive_bytes_total{{container_label_com_docker_swarm_service_name="{SERVICE_NAME}"}}[1m]
    )[2m:]
  )
)
"""

# ============================
# HELPERS
# ============================

def prom_query(query):
    try:
        resp = requests.get(
            f"{PROM_URL}/api/v1/query",
            params={"query": query},
            timeout=3
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("result", [])
    except Exception as e:
        print("Prometheus error:", e)
        return []

def extract_task_index(task_name):
    """
    task format: openslide_iiif-openslide.3.xyz123
    index = 3
    """
    parts = task_name.split(".")
    if len(parts) >= 2:
        return parts[1]
    return None

# ============================
# WEIGHT CALCULATION (DWRR)
# ============================

def calc_weight(cpu, mem, net):
    # Normalize CPU
    cpu_pct = min(cpu / CPU_LIMIT, 1.0)
    cpu_score = 1 - cpu_pct

    # Normalize Memory
    mem_pct = min(mem / MEM_LIMIT, 1.0)
    mem_score = 1 - mem_pct

    # Normalize Network receive
    net_pct = min(net / NET_LIMIT, 1.0)
    net_score = 1 - net_pct

    # Final DWRR score
    final_score = (
        0.4 * cpu_score +
        0.3 * mem_score +
        0.3 * net_score
    )

    weight = max(1, int(final_score * 256))
    return weight

# ============================
# MAIN ENDPOINT
# ============================

@app.route("/weight")
def weight():
    cpu_data = prom_query(QUERY_CPU)
    mem_data = prom_query(QUERY_MEM)
    net_data = prom_query(QUERY_NET)

    weights = {}

    # Convert list to dict for fast lookup
    cpu_map = {d["metric"]["container_label_com_docker_swarm_task_name"]: float(d["value"][1]) for d in cpu_data}
    mem_map = {d["metric"]["container_label_com_docker_swarm_task_name"]: float(d["value"][1]) for d in mem_data}
    net_map = {d["metric"]["container_label_com_docker_swarm_task_name"]: float(d["value"][1]) for d in net_data}

    # Combine metrics by task
    all_tasks = set(cpu_map.keys()) | set(mem_map.keys()) | set(net_map.keys())

    for task in all_tasks:
        idx = extract_task_index(task)
        if not idx:
            continue

        cpu_val = cpu_map.get(task, 0.0)
        mem_val = mem_map.get(task, 0.0)
        net_val = net_map.get(task, 0.0)

        w = calc_weight(cpu_val, mem_val, net_val)

        srv_name = f"iiif{idx}"
        weights[srv_name] = w

        print(f"[{srv_name}] CPU={cpu_val:.4f}, MEM={mem_val}, NET={net_val:.2f}, Weight={w}")

    return {"weights": weights}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9200)

