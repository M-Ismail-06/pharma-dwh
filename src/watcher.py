import threading
import time
from pathlib import Path

import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import DROPZONE, API_URL

in_flight = set()
lock = threading.Lock()


def wait_until_stable(path, checks=3, interval=1.5):
    """A file that is still being copied keeps growing; wait until it stops."""
    last, stable = -1, 0
    while stable < checks:
        try:
            size = Path(path).stat().st_size
        except FileNotFoundError:
            return False
        stable = stable + 1 if size == last else 0
        last = size
        time.sleep(interval)
    return True


def process(path):
    with lock:
        if path in in_flight:
            return
        in_flight.add(path)
    try:
        if not wait_until_stable(path):
            return
        print(f"[watcher] sending {Path(path).name} to the API ...")
        r = requests.post(API_URL, json={"file_path": str(path)}, timeout=3600)
        print(f"[watcher] result: {r.json()}")
    except Exception as e:
        print(f"[watcher] ERROR for {path}: {e}")
    finally:
        with lock:
            in_flight.discard(path)


class Handler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".csv"):
            threading.Thread(target=process, args=(event.src_path,), daemon=True).start()


if __name__ == "__main__":
    DROPZONE.mkdir(parents=True, exist_ok=True)
    # pick up files that arrived while the watcher was off
    for f in DROPZONE.glob("*.csv"):
        threading.Thread(target=process, args=(str(f),), daemon=True).start()

    observer = Observer()
    observer.schedule(Handler(), str(DROPZONE), recursive=False)
    observer.start()
    print(f"[watcher] watching {DROPZONE}  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()