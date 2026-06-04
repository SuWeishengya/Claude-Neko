"""Claude Desktop Buddy launcher - runs all 3 processes silently"""
import subprocess, time
from pathlib import Path

base = Path(__file__).parent
python = base / "venv" / "Scripts" / "python.exe"

procs = []
for script in ["server.py", "cc_switch_monitor.py", "buddy_widget.py"]:
    p = subprocess.Popen(
        [str(python), str(base / script)],
        cwd=str(base),
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs.append(p)
    print(f"Started {script} (PID {p.pid})")
    time.sleep(2)

# write PIDs for stop script
(base / "pids.txt").write_text("\n".join(str(p.pid) for p in procs))
print(f"\nAll started! PIDs saved to pids.txt")
