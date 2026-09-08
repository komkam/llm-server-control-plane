import subprocess
import time
import requests


OLLAMA_URL = "http://localhost:11434/api/chat"
ROUTER_URL = "http://localhost:5000/v1/chat/completions"

QWEN_MODEL = "qwen2.5:7b"

TIMEOUT = 120


def get_failed_services():

    try:
        result = subprocess.run(
            [
                "systemctl",
                "--failed",
                "--no-pager"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except Exception as e:
        return {"error": str(e)}


def get_llm_services():

    try:
        result = subprocess.run(
            [
                "systemctl",
                "status",
                "ollama",
                "router",
                "--no-pager"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except Exception as e:
        return {"error": str(e)}


def benchmark_qwen():

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: OK"
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 8
        }
    }

    start = time.perf_counter()

    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=TIMEOUT
        )

        total = time.perf_counter() - start
        data = response.json()

        if response.status_code != 200:

            return {
                "model": QWEN_MODEL,
                "status": response.status_code,
                "error": data,
                "total_time_ms": round(total * 1000, 2)
            }

        eval_count = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 0)

        generation_tok_s = None

        if eval_count and eval_duration_ns:

            generation_tok_s = (
                eval_count /
                (eval_duration_ns / 1_000_000_000)
            )

        return {

            "model": QWEN_MODEL,

            "status": response.status_code,

            "total_time_ms":
                round(total * 1000, 2),

            "prompt_tokens":
                data.get("prompt_eval_count"),

            "generated_tokens":
                eval_count,

            "prompt_eval_time_ms":
                round(
                    data.get(
                        "prompt_eval_duration",
                        0
                    ) / 1_000_000,
                    2
                ),

            "generation_time_ms":
                round(
                    eval_duration_ns / 1_000_000,
                    2
                ),

            "generation_tokens_per_second":
                round(
                    generation_tok_s,
                    2
                ) if generation_tok_s else None
        }

    except Exception as e:

        return {
            "model": QWEN_MODEL,
            "error": str(e)
        }



def benchmark_router(model, prompt):

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False,
        "temperature": 0
    }

    start = time.perf_counter()

    try:

        response = requests.post(
            ROUTER_URL,
            json=payload,
            headers={
                "Authorization": "Bearer local-llm"
            },
            timeout=TIMEOUT
        )

        total = time.perf_counter() - start

        return {
            "model": model,
            "status": response.status_code,
            "total_time_ms":
                round(total * 1000, 2)
        }

    except Exception as e:

        return {
            "model": model,
            "error": str(e)
        }


def get_llm_latency():
    """Benchmark the active Qwen backend and its Router path only."""
    prompt = "Reply with exactly: OK"
    qwen = benchmark_qwen()
    router_qwen = benchmark_router("qwen-engineer", prompt)
    result = {"direct": {"qwen": qwen}, "router": {"qwen": router_qwen}, "overhead": {}}
    if qwen.get("status") == 200 and router_qwen.get("status") == 200:
        result["overhead"]["router_qwen_ms"] = round(router_qwen["total_time_ms"] - qwen["total_time_ms"], 2)
    return result
