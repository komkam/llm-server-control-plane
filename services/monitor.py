import os
import json
import time
import socket
import psutil
import shutil
import subprocess
import tempfile
import grp
from datetime import datetime

try:
    import pynvml
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False


BASE_DIR = "/opt/llm-server"

DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

INTERVAL = 2
MAX_HISTORY = 600


os.makedirs(DATA_DIR, exist_ok=True)


history = []


def atomic_write(path, data):
    directory = os.path.dirname(path)

    fd, temp_path = tempfile.mkstemp(
        dir=directory,
        prefix=".tmp_"
    )

    try:
        with os.fdopen(fd, "w") as f:
            json.dump(
                data,
                f,
                indent=2
            )

        os.chmod(temp_path, 0o640)
        os.chown(temp_path, -1, grp.getgrnam("dashboard-agent").gr_gid)

        os.replace(
            temp_path,
            path
        )

    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)



def load_history():

    global history

    if os.path.exists(HISTORY_FILE):

        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)

        except Exception:
            history = []



def save_history():

    atomic_write(
        HISTORY_FILE,
        history[-MAX_HISTORY:]
    )



def get_time():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )



def get_cpu():

    return {
        "percent": psutil.cpu_percent()
    }



def get_ram():

    mem = psutil.virtual_memory()

    return {
        "percent": round(mem.percent, 1),
        "used": round(
            mem.used / 1024**3,
            2
        ),
        "total": round(
            mem.total / 1024**3,
            2
        )
    }



def get_disk():

    disk = shutil.disk_usage("/")

    total = disk.total / 1024**3
    used = disk.used / 1024**3

    return {
        "percent": round(
            used / total * 100,
            1
        ),
        "used": round(
            used,
            2
        ),
        "total": round(
            total,
            2
        )
    }


def init_gpu():

    if not NVML_AVAILABLE:
        return False

    try:
        pynvml.nvmlInit()
        return True

    except Exception:
        return False



GPU_READY = init_gpu()



def get_gpu():

    if not GPU_READY:

        return {
            "name": "N/A",
            "vram_used": 0,
            "vram_total": 0,
            "load": 0,
            "temperature": 0,
            "power": 0,
            "clock": 0,
            "memory_clock": 0
        }


    try:

        handle = pynvml.nvmlDeviceGetHandleByIndex(0)

        name = pynvml.nvmlDeviceGetName(
            handle
        )

        if isinstance(name, bytes):
            name = name.decode()


        mem = pynvml.nvmlDeviceGetMemoryInfo(
            handle
        )


        util = pynvml.nvmlDeviceGetUtilizationRates(
            handle
        )


        temp = pynvml.nvmlDeviceGetTemperature(
            handle,
            pynvml.NVML_TEMPERATURE_GPU
        )


        try:
            power = (
                pynvml.nvmlDeviceGetPowerUsage(
                    handle
                ) / 1000
            )

        except Exception:
            power = 0


        try:
            clock = pynvml.nvmlDeviceGetClockInfo(
                handle,
                pynvml.NVML_CLOCK_GRAPHICS
            )

        except Exception:
            clock = 0


        try:
            mem_clock = pynvml.nvmlDeviceGetClockInfo(
                handle,
                pynvml.NVML_CLOCK_MEM
            )

        except Exception:
            mem_clock = 0



        return {

            "name": name,

            "vram_used": round(
                mem.used / 1024**3,
                2
            ),

            "vram_total": round(
                mem.total / 1024**3,
                2
            ),

            "load": util.gpu,

            "temperature": temp,

            "power": round(
                power,
                2
            ),

            "clock": clock,

            "memory_clock": mem_clock

        }


    except Exception:

        return {

            "name": "N/A",
            "vram_used": 0,
            "vram_total": 0,
            "load": 0,
            "temperature": 0,
            "power": 0,
            "clock": 0,
            "memory_clock": 0

        }



def get_network():

    net = psutil.net_io_counters()


    return {

        "sent": round(
            net.bytes_sent / 1024**2,
            2
        ),

        "recv": round(
            net.bytes_recv / 1024**2,
            2
        )

    }


def get_system():

    return {

        "time": get_time(),

        "hostname": socket.gethostname(),

        "cpu": get_cpu(),

        "ram": get_ram(),

        "disk": get_disk(),

        "network": get_network(),

        "gpu": get_gpu()

    }



def check_service(name):

    result = {

        "name": name,

        "status": "unknown"

    }


    try:

        output = os.popen(
            f"systemctl is-active {name}"
        ).read().strip()


        if output == "active":
            result["status"] = "running"

        else:
            result["status"] = output


    except Exception:

        result["status"] = "error"


    return result


def check_docker(name):

    try:

        output = subprocess.check_output(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                name
            ],
            text=True
        ).strip()


        if output == "true":

            return {
                "name": name,
                "status": "running"
            }

        else:

            return {
                "name": name,
                "status": "stopped"
            }


    except Exception:

        return {
            "name": name,
            "status": "not found"
        }


def get_services():

    system_services = [
        "llama-server",
        "router"
        , "agent",
        "dashboard",
        "autonomy",
        "ollama",
        "monitor",
    ]


    docker_services = [

        "open-webui"

    ]


    result = []


    for service in system_services:

        result.append(
            check_service(service)
        )


    for container in docker_services:

        result.append(
            check_docker(container)
        )


    return result


def collect():

    data = get_system()


    data["services"] = get_services()


    return data



def save_state(data):

    atomic_write(
        STATE_FILE,
        data
    )



def append_history(data):

    global history


    item = {

        "time": data["time"],

        "cpu": data["cpu"]["percent"],

        "ram": data["ram"]["percent"],

        "gpu": {

            "load": data["gpu"]["load"],

            "temperature": data["gpu"]["temperature"],
            "vram_used": data["gpu"]["vram_used"],
            "power": data["gpu"]["power"]

        }

    }


    history.append(item)


    if len(history) > MAX_HISTORY:

        del history[
            :-MAX_HISTORY
        ]



def run():

    load_history()


    while True:

        try:

            data = collect()


            save_state(
                data
            )


            append_history(
                data
            )


            save_history()


        except Exception as e:

            print(
                "Monitor error:",
                e
            )


        time.sleep(
            INTERVAL
        )


if __name__ == "__main__":

    run()
