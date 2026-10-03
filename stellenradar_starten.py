"""Startet das Dashboard und öffnet es im Browser."""
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ORDNER = Path(__file__).resolve().parent
PORT = 8501


def browser_oeffnen():
    time.sleep(4)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    print("Stellen-Radar startet ...")
    print(f"Falls sich kein Browser öffnet: http://localhost:{PORT} im Browser aufrufen.")
    print("Zum Beenden dieses Fenster schließen (oder Strg+C drücken).\n")
    threading.Thread(target=browser_oeffnen, daemon=True).start()
    try:
        subprocess.call([sys.executable, "-m", "streamlit", "run", str(ORDNER / "dashboard.py"),
                         "--server.port", str(PORT), "--server.headless", "true"], cwd=ORDNER)
    except KeyboardInterrupt:
        pass
