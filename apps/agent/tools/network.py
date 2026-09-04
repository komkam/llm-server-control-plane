import time
import requests


ENDPOINTS = {

    "ollama": "http://localhost:11434/api/tags",

    "llama.cpp": "http://localhost:8082/health",

    "router": "http://localhost:5000/health",

}


def get_endpoint_health():

    results = {}

    for name, url in ENDPOINTS.items():

        start = time.perf_counter()

        try:

            response = requests.get(
                url,
                timeout=10
            )

            elapsed = time.perf_counter() - start

            results[name] = {

                "url": url,

                "status": response.status_code,

                "latency_ms": round(
                    elapsed * 1000,
                    2
                ),

            }

        except Exception as e:

            elapsed = time.perf_counter() - start

            results[name] = {

                "url": url,

                "status": None,

                "latency_ms": round(
                    elapsed * 1000,
                    2
                ),

                "error": str(e)

            }

    return results
