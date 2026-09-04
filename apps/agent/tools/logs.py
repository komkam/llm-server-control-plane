import subprocess


def get_system_logs(lines=100):

    try:

        result = subprocess.run(
            [
                "journalctl",
                "-n",
                str(lines),
                "--no-pager",
                "-o",
                "short-iso"
            ],
            capture_output=True,
            text=True,
            timeout=20
        )

        return {
            "lines": lines,
            "returncode": result.returncode,
            "stdout": result.stdout[-16000:],
            "stderr": result.stderr[-4000:]
        }

    except Exception as e:

        return {
            "error": str(e)
        }
