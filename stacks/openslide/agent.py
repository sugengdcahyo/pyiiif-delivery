from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ============================
# CONFIG
# ============================
PROM_URL = os.getenv("PROM_URL", "http://imgbox2:9090")
SERVICE_NAME = os.getenv("SERVICE_NAME", "openslide_iiif-openslide")

CPU_LIMIT = float(os.getenv("CPU_LIMIT", 2.0))          # core limit
MEM_LIMIT = float(os.getenv("MEM_LIMIT", 2 * 1024**3))  # default 2GB
NET_LIMIT = float(os.getenv("NET_LIMIT", 5 * 1024**2))  # default 5MB/s

CPU_WEIGHT = float(os.getenv("CPU_WEIGHT", 0.6))
NET_WEIGHT = float(os.getenv("NET_WEIGHT", 0.3))
MEM_WEIGHT = float(os.getenv("MEM_WEIGHT", 0.1))

DEFAULT_SMOOTH_ALPHA = float(os.getenv("SMOOTH_ALPHA", 0.3))

# smoothing state untuk DSWRR
last_weights = {}  # key: "iiif{idx}" -> last_smooth_weight (int 1..256)

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

def prom_query(query: str):
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

def extract_task_index(task_name: str):
    """
    task format: openslide_iiif-openslide.3.xyz123
    index = 3
    """
    parts = task_name.split(".")
    if len(parts) >= 3:
        idx = parts[1]
        # guard: pastikan numeric
        return idx if idx.isdigit() else None
    return None

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

# ============================
# WEIGHT CALCULATION
# ============================

def calc_raw_weight(cpu: float, mem: float, net: float) -> int:
    # Normalize (0..1)
    cpu_pct = min(cpu / CPU_LIMIT, 1.0) if CPU_LIMIT > 0 else 1.0
    mem_pct = min(mem / MEM_LIMIT, 1.0) if MEM_LIMIT > 0 else 1.0
    net_pct = min(net / NET_LIMIT, 1.0) if NET_LIMIT > 0 else 1.0

    # Score: makin kecil pemakaian -> makin tinggi score
    cpu_score = 1 - cpu_pct
    mem_score = 1 - mem_pct
    net_score = 1 - net_pct

    final_score = (
        CPU_WEIGHT * cpu_score +
        MEM_WEIGHT * mem_score +
        NET_WEIGHT * net_score
    )

    # Map to 1..256
    weight = int(final_score * 256)
    return clamp(weight, 1, 256)

def smooth_weight(server_name: str, raw: int, alpha: float) -> int:
    """
    DSWRR smoothing: new = alpha*raw + (1-alpha)*old
    """
    alpha = clamp(alpha, 0.0, 1.0)
    old = last_weights.get(server_name, raw)
    smooth = (alpha * raw) + ((1 - alpha) * old)
    smooth_int = int(clamp(smooth, 1, 256))
    last_weights[server_name] = smooth_int
    return smooth_int

def build_metric_maps():
    cpu_data = prom_query(QUERY_CPU)
    mem_data = prom_query(QUERY_MEM)
    net_data = prom_query(QUERY_NET)

    # Convert list -> dict
    cpu_map = {
        d["metric"]["container_label_com_docker_swarm_task_name"]: float(d["value"][1])
        for d in cpu_data
        if "metric" in d and "container_label_com_docker_swarm_task_name" in d["metric"]
    }
    mem_map = {
        d["metric"]["container_label_com_docker_swarm_task_name"]: float(d["value"][1])
        for d in mem_data
        if "metric" in d and "container_label_com_docker_swarm_task_name" in d["metric"]
    }
    net_map = {
        d["metric"]["container_label_com_docker_swarm_task_name"]: float(d["value"][1])
        for d in net_data
        if "metric" in d and "container_label_com_docker_swarm_task_name" in d["metric"]
    }

    all_tasks = set(cpu_map.keys()) | set(mem_map.keys()) | set(net_map.keys())
    return all_tasks, cpu_map, mem_map, net_map

def compute_weights(algo: str, alpha: float, include_raw: bool):
    """
    algo: "dwrr" atau "dswrr"
    """
    all_tasks, cpu_map, mem_map, net_map = build_metric_maps()

    weights = {}
    debug = {}

    for task in sorted(all_tasks):
        idx = extract_task_index(task)
        if not idx:
            continue

        cpu = cpu_map.get(task, 0.0)
        mem = mem_map.get(task, 0.0)
        net = net_map.get(task, 0.0)

        raw_w = calc_raw_weight(cpu, mem, net)
        server = f"iiif{idx}"

        if algo == "dswrr":
            w = smooth_weight(server, raw_w, alpha)
        else:
            w = raw_w  # dwrr

        weights[server] = w

        # debug opsional
        debug[server] = {
            "task": task,
            "cpu": round(cpu, 6),
            "mem": mem,
            "net": round(net, 2),
            "weight": w,
            **({"raw": raw_w} if include_raw else {})
        }

    return weights, debug

def parse_bool(v: str) -> bool:
    return str(v).lower() in ("1", "true", "yes", "y", "on")

# ============================
# ROUTES
# ============================

@app.route("/weight/", strict_slashes=False)
def weight_unified():
    algo = (request.args.get("algo", "dswrr") or "dswrr").lower()
    if algo not in ("dwrr", "dswrr"):
        return jsonify({
            "error": "Invalid algo. Use algo=dwrr or algo=dswrr"
        }), 400

    # reset smoothing state jika diminta
    if parse_bool(request.args.get("reset", "0")):
        last_weights.clear()

    include_raw = parse_bool(request.args.get("include_raw", "0"))

    alpha = request.args.get("alpha", None)
    alpha = float(alpha) if alpha is not None else DEFAULT_SMOOTH_ALPHA

    weights, debug = compute_weights(algo=algo, alpha=alpha, include_raw=include_raw)

    return jsonify({
        "service": SERVICE_NAME,
        "algo": algo,
        "alpha": alpha if algo == "dswrr" else None,
        "weights": weights,
        "details": debug
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9200)
