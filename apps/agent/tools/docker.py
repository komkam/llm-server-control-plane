import subprocess


def get_docker_info():

    try:

        result = subprocess.run(
            [
                "docker",
                "ps",
                "--format",
                "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
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

        return {
            "error": str(e)
        }


def get_docker_stats():

    try:

        result = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream"
            ],
            capture_output=True,
            text=True,
            timeout=20
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except Exception as e:

        return {
            "error": str(e)
        }


def get_docker_logs(container="open-webui", lines=100):

    try:

        result = subprocess.run(
            [
                "docker",
                "logs",
                "--tail",
                str(lines),
                container
            ],
            capture_output=True,
            text=True,
            timeout=20
        )

        return {
            "container": container,
            "lines": lines,
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-4000:]
        }

    except Exception as e:

        return {
            "container": container,
            "error": str(e)
        }


def get_docker_images():

    try:

        result = subprocess.run(
            [
                "docker",
                "images",
                "--format",
                "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}"
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

        return {
            "error": str(e)
        }
