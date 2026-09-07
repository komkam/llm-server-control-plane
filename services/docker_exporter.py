#!/usr/bin/env python3
"""Read-only Docker container resource exporter for Prometheus."""

import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def metric_number(value: str) -> float:
    return float(value.strip().removesuffix("%"))


def metrics() -> str:
    command = ["/usr/bin/docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}"]
    try:
        output = subprocess.run(command, capture_output=True, text=True, check=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return "# HELP llm_docker_exporter_up Whether Docker statistics are available.\n# TYPE llm_docker_exporter_up gauge\nllm_docker_exporter_up 0\n"
    lines = [
        "# HELP llm_docker_exporter_up Whether Docker statistics are available.",
        "# TYPE llm_docker_exporter_up gauge",
        "llm_docker_exporter_up 1",
        "# HELP llm_docker_container_cpu_percent Docker container CPU percentage.",
        "# TYPE llm_docker_container_cpu_percent gauge",
        "# HELP llm_docker_container_memory_percent Docker container memory percentage.",
        "# TYPE llm_docker_container_memory_percent gauge",
    ]
    for row in output.splitlines():
        try:
            name, cpu, memory = row.split("|", 2)
            label = name.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'llm_docker_container_cpu_percent{{container="{label}"}} {metric_number(cpu)}')
            lines.append(f'llm_docker_container_memory_percent{{container="{label}"}} {metric_number(memory)}')
        except (ValueError, TypeError):
            continue
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
    ThreadingHTTPServer((os.environ.get("METRICS_HOST", "172.17.0.1"), int(os.environ.get("METRICS_PORT", "9402"))), Handler).serve_forever()
