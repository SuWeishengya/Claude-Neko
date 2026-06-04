"""Stop all Claude Desktop Buddy processes"""
import os, subprocess
from pathlib import Path

base = Path(__file__).parent
pids_file = base / "pids.txt"

killed = 0

# Kill by PID file
if pids_file.exists():
    for line in pids_file.read_text().strip().splitlines():
        pid = line.strip()
        if pid.isdigit():
            try:
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                print(f"Killed PID {pid}")
                killed += 1
            except Exception:
                pass
    pids_file.unlink()

# Kill by command line as fallback
try:
    result = subprocess.run(
        ["wmic", "process", "where",
         "CommandLine like '%claude-desktop-buddy%' and Name like '%python%'",
         "get", "ProcessId"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            subprocess.run(["taskkill", "/F", "/PID", line], capture_output=True)
            print(f"Killed PID {line} (wmic)")
            killed += 1
except Exception:
    pass

print(f"\nDone. Killed {killed} process(es).")
