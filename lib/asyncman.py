import sys
import asyncio
import signal
from time import time, sleep
from enum import Enum
from threading import Thread, Event
import traceback

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

class AsyncTaskManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self._start_loop, daemon=True)
        self.tasks = {}

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self):
        self.thread.start()

    def run(self, name, coro):
        xreport("AsynctaskManager", "run", f"Submitting coroutine '{name}' to the loop.", blue=True,)
        """Submit a coroutine to the loop."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = future
        return future

    def shutdown(self, timeout=5):
        """Cancel all running tasks and stop the loop."""
        for name, task in self.tasks.items():
            xreport("AsynctaskManager", "shutdown", f"task {name} done={task.done()}", blue=True,)
            if not task.done():
                xreport("AsynctaskManager", "shutdown", f"Cancelling task '{name}'.", blue=True,)
                task.cancel()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout)


