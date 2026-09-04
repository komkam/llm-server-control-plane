import subprocess


def run_command(command, timeout=10):

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-4000:]
        }

    except Exception as e:

        return {
            "error": str(e)
        }


def get_system_info():

    return run_command([
        "uptime"
    ])


def get_memory_info():

    return run_command([
        "free",
        "-h"
    ])


def get_disk_info():

    return run_command([
        "df",
        "-h"
    ])


def get_llm_processes():

    return run_command([
        "ps",
        "-eo",
        "pid,pcpu,pmem,rss,comm,args",
        "--sort=-pcpu"
    ])


def get_cpu_info():

    return run_command([
        "bash",
        "-c",
        "echo '=== CPU ==='; "
        "lscpu | grep -E 'Model name|CPU\\(s\\)|Core\\(s\\) per socket|Thread\\(s\\) per core'; "
        "echo; "
        "echo '=== Load ==='; "
        "uptime"
    ])


def get_uptime_info():

    return run_command([
        "uptime",
        "-p"
    ])
