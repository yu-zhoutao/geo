from __future__ import annotations

import signal
import time


running = True


def stop(_signal: int, _frame: object) -> None:
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

while running:
    time.sleep(0.5)
