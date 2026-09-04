import subprocess


def parse_number(value):
    value = value.strip()

    if value.upper() in (
        "N/A",
        "[N/A]",
        "NA",
        "",
        "UNKNOWN"
    ):
        return None

    try:
        return float(value)
    except ValueError:
        return value


def get_gpu_info():

    try:

        query = (
            "name,"
            "driver_version,"
            "temperature.gpu,"
            "utilization.gpu,"
            "power.draw,"
            "power.limit,"
            "memory.total,"
            "memory.used,"
            "memory.free,"
            "pstate"
        )

        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return {
                "error": result.stderr.strip(),
                "returncode": result.returncode
            }

        line = result.stdout.strip()

        if not line:
            return {
                "error": "nvidia-smi returned no GPU data"
            }

        values = [
            x.strip()
            for x in line.split(",")
        ]

        if len(values) < 10:
            return {
                "error": "Unexpected nvidia-smi output",
                "raw": result.stdout
            }

        gpu = {
            "name": values[0],
            "driver": values[1],

            "temperature_c":
                parse_number(values[2]),

            "utilization_percent":
                parse_number(values[3]),

            "power_w":
                parse_number(values[4]),

            "power_limit_w":
                parse_number(values[5]),

            "vram_total_mib":
                parse_number(values[6]),

            "vram_used_mib":
                parse_number(values[7]),

            "vram_free_mib":
                parse_number(values[8]),

            "performance_state":
                values[9]
        }

        # --------------------------------------------------
        # GPU processes
        # --------------------------------------------------

        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,name,used_memory",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        processes = []

        if proc.returncode == 0:

            for line in proc.stdout.splitlines():

                line = line.strip()

                if not line:
                    continue

                parts = [
                    x.strip()
                    for x in line.split(",")
                ]

                if len(parts) >= 3:

                    processes.append({
                        "pid": parts[0],
                        "name": parts[1],
                        "memory_mib":
                            parse_number(parts[2])
                    })

        gpu["processes"] = processes

        # --------------------------------------------------
        # Derived information
        # --------------------------------------------------

        if (
            gpu["vram_total_mib"] is not None
            and gpu["vram_used_mib"] is not None
        ):
            gpu["vram_used_percent"] = round(
                gpu["vram_used_mib"]
                / gpu["vram_total_mib"]
                * 100,
                1
            )
        else:
            gpu["vram_used_percent"] = None

        return gpu

    except Exception as e:

        return {
            "error": str(e)
        }