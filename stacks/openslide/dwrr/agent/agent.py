from flask import Flask
import requests
import os
import re

app = Flask(__name__)

# Konfigurasi dari environment variable
PROM_URL = os.getenv("PROM_URL", "http://imgbox2:9090")
SERVICE_NAME = os.getenv("SERVICE_NAME", "openslide_iiif-openslide")
CPU_LIMIT = float(os.getenv("CPU_LIMIT", 2.0))   # jumlah core per container

def query_cpu():
    query = f"""
    sum by (container_label_com_docker_swarm_task_name) (
      avg_over_time(
        irate(
          container_cpu_usage_seconds_total{{container_label_com_docker_swarm_service_name="{SERVICE_NAME}"}}[1m]
        )[2m:]
      )
    )
    """
    try:
        resp = requests.get(
            f"{PROM_URL}/api/v1/query",
            params={"query": query},
            timeout=3
        )
        resp.raise_for_status()
        results = resp.json().get("data", {}).get("result", [])
        print(resp.json())
        return results
    except Exception as e:
        print("CPU query error:", e)
        return []

@app.route("/weight")
def weight():
    results = query_cpu()
    weights = {}

    for i, r in enumerate(results, start=1):
        task = r["metric"]["container_label_com_docker_swarm_task_name"]
        val = float(r["value"][1])

        # Normalisasi CPU usage jadi persentase
        cpu_percent = (val / CPU_LIMIT)
        if cpu_percent > 1: 
            cpu_percent = 1.0

        # Bobot: semakin tinggi load → semakin rendah weight
        weight = max(1, round((1 - cpu_percent) * 100, 2))

        # print(f"cpu : {cpu_percent * 100} % \nweight : {weight}")
        
        m = re.search(r"\.(\d+)\.", task)
        if m:
            idx = m.group(1)
            srv_name = f"iiif{idx}"
            weights[srv_name] = weight

            print(f"Task={task}, CPU={val:.4f}, Weight={weight}")

    return {"weights": weights}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9200)

