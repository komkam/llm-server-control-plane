#!/usr/bin/env python3
"""Small read-only NVIDIA metrics exporter; avoids a privileged GPU metrics container."""

import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def metrics() -> str:
    command = ["/usr/bin/nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw", "--format=csv,noheader,nounits"]
    try:
        output = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return "# HELP llm_gpu_exporter_up Whether NVIDIA metrics are available.\n# TYPE llm_gpu_exporter_up gauge\nllm_gpu_exporter_up 0\n"
    lines = ["# HELP llm_gpu_exporter_up Whether NVIDIA metrics are available.", "# TYPE llm_gpu_exporter_up gauge", "llm_gpu_exporter_up 1"]
    definitions = (("llm_gpu_utilization_percent", "GPU utilization percentage"), ("llm_gpu_memory_used_bytes", "GPU memory used in bytes"), ("llm_gpu_memory_total_bytes", "GPU memory total in bytes"), ("llm_gpu_temperature_celsius", "GPU temperature in Celsius"), ("llm_gpu_power_watts", "GPU power draw in Watts"))
    for name, description in definitions:
        lines.extend((f"# HELP {name} {description}", f"# TYPE {name} gauge"))
    for row in output.splitlines():
        index, utilization, used, total, temperature, power = (part.strip() for part in row.split(","))
        labels = f'{{gpu="{index}"}}'
        lines.extend((
            f"llm_gpu_utilization_percent{labels} {utilization}",
            f"llm_gpu_memory_used_bytes{labels} {float(used) * 1024 * 1024}",
            f"llm_gpu_memory_total_bytes{labels} {float(total) * 1024 * 1024}",
            f"llm_gpu_temperature_celsius{labels} {temperature}",
            f"llm_gpu_power_watts{labels} {power}",
        ))
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/metrics", "/health"):
            self.send_error(404)
            return
        body = ("ok\n" if self.path == "/health" else metrics()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("METRICS_HOST", "172.17.0.1"), int(os.environ.get("METRICS_PORT", "9401"))), Handler).serve_forever()
