import sys
import asyncio
import signal
from time import time, sleep
from enum import Enum
from threading import Thread, Event
import traceback

from lib.log import setup_logger, xreport
from lib.asyncman import AsyncTaskManager

import logging
if __name__ == '__main__':
    logger = setup_logger()
else:
    logger = logging.getLogger(__name__)

logger.info("LOGGER TEST")

class Shutdown:
    """
    Shutdown class to handle graceful shutdowns and signal handling.

    This class listens for SIGINT (Ctrl+C) and provides a way to wait for shutdown events to be set.

    Two events are provided:
      - `_sigintEvent`: Set when a SIGINT is received.
      - `_shutdownEvent`: Set when a shutdown is requested, which is two SIGINTs seen within two seconds.

    XXX Python 3.13 Queue.shutdown
    Python 3.13 has added Queue.shutdown() which can be used to signal callers of Queue.put() or Queue.wait().

    We can use this by implementing a get() function that adds the queue to the shutdown queues list. And
    shutdown can then call Queue.shutdown() to signal all waiting tasks that they should stop. Allowing them
    to use a simpler while myQueue.get(): loop instead of doing a wait(timeout) on the shutdown event.

    """

    def __init__(self):
        self.name = 'AEvents'
        self.last_sigint = None
        self._sigintEvent = Event()
        self._sigintEvent.clear()
        #self._interruptEvent = Event()
        #self._interruptEvent.clear()
        self._shutdownEvent = Event()
        self._shutdownEvent.clear()
        self._interruptEvents = []
        if sys.version_info >= (3, 13): 
            self._queues = []  # List of queues to shutdown

        def sigint_handler():
            sys.stdout.write('\r' + ' ' * 80 + '\r')  # Clear the line
            sys.stdout.flush()
            #xreport('sigint_handler', 'SIGINT received', green=True)
            if self.last_sigint and (time() - self.last_sigint) < 4:
                xreport('sigint_handler', 'SIGINT received', '< 4 seconds, shutting down...', red=True, )
                self._shutdownEvent.set()
                if sys.version_info >= (3, 13): 
                    for queue in self._queues:
                        try:
                            xreport('sigint_handler', 'Shutting down queue', yellow=True)
                            queue.shutdown(immediate=True)  
                        except Exception as e:
                            xreport('sigint_handler', 'Error shutting down queue', f'{e}', red=True)

            if True:
                xreport('sigint_handler', 'SIGINT received,' 'interrupting', yellow=True,)
                for event in self._interruptEvents:
                    event.set()
                self._interruptEvents = []
            self._sigintEvent.set()
            self.last_sigint = time()

        signal.signal(signal.SIGINT, lambda sig, frame: sigint_handler())

    def events(self):
        return self._sigintEvent, self._shutdownEvent

    #def sigintClear(self):
    #    self._sigintEvent.clear()

    def set(self, msg=''):
        xreport('Shutdown.set', msg, f"shutdown: {self._shutdownEvent.is_set()} sigint: {self._sigintEvent.is_set()}", red=True)
        self._shutdownEvent.set()
        self._sigintEvent.set()
        xreport('Shutdown.set', msg, f"shutdown: {self._shutdownEvent.is_set()} sigint: {self._sigintEvent.is_set()}", red=True)

    def is_set(self):
        return self._shutdownEvent.is_set()

    def wait(self, interruptEvent, timeout=None):
        #xreport('Shutdown.wait', f'waiting for interruptEvent {interruptEvent}','with timeout {timeout}')
        if not isinstance(interruptEvent, Event):
            self._interruptEvents.append(interruptEvent)
        #xreport('Shutdown.wait', '', f'current interruptEvents {self._interruptEvents}')
        return self._sigintEvent.wait(timeout=timeout) 

    def add_queue(self, queue):
        """Add a queue to the shutdown list."""
        if sys.version_info >= (3, 13): 
            self._queues.append(queue)

    def remove_queue(self, queue):
        """Remove a queue from the shutdown list."""
        if sys.version_info >= (3, 13): 
            if queue in self._queues:
                self._queues.remove(queue)



if __name__ == '__main__':

    logger.info("Starting shutdown example")
    #setup_logger()
    #logger = logging.getLogger(__name__).info("Starting shutdown example")

    # async task to do wait with timeouts on its private interrupt until shutdownEvent is set.
    async def asynctask(shutdown, sigintEvent, shutdownEvent):
        try:
            asyncEvent1 = asyncio.Event()
            while not shutdownEvent.is_set():
                shutdown.wait(asyncEvent1, timeout=3)
                asyncEvent1.clear()
                xreport('asynctask', 'waiting', f'sigint {sigintEvent.is_set()} shutdown ({shutdownEvent.is_set()}) ...', )
                if sigintEvent.is_set():
                    sigintEvent.clear()
                    xreport('asynctask', 'interrupted', yellow=True)
                    asyncEvent1.set()
        except Exception as e:
            xreport('asynctask', 'Exception', f'{e}', red=True)
            print(f"Exception in asynctask: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return

    # Timer thread to do wait with timeouts on its private interrupt until shutdownEvent is set.
    def timerthread(shutdown, sigintEvent, shutdownEvent):

        print(f"timerthread started with sigintEvent: {sigintEvent} shutdownEvent: {shutdownEvent}", file=sys.stderr)
        try:
            interruptEvent1 = Event()

            while not shutdownEvent.is_set():
                shutdown.wait(interruptEvent1, timeout=3)
                sigintEvent.clear()
                print('timerthread -------------------------')
                print(f'timerthread running sigint {sigintEvent.is_set()} interrupt ({interruptEvent1.is_set()}) shutdown ({shutdownEvent.is_set()}) ...', 
                      file=sys.stderr)
                if interruptEvent1.is_set():
                    interruptEvent1.clear()
                    print('timerthread interrupted ...', file=sys.stderr)

        except Exception as e:
            print(f"Exception in timerthread: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

        print('timerthread shutdown ... AAAA', file=sys.stderr)


    shutdown = Shutdown()
    events = shutdown.events()
    asycman = AsyncTaskManager()
    asycman.start()

    if True:
        # Launch asyncio task
        asycman.run(asynctask(shutdown, events[0], events[1]))

    asyncio_future = None
    if False:
        # Launch asyncio loop in a separate thread
        async_loop = asyncio.new_event_loop()
        asyncio_thread = Thread(target=async_loop.run_forever, daemon=True)
        asyncio_thread.start()
        # Submit coroutine to the async loop
        asyncio_future = asyncio.run_coroutine_threadsafe(
            asynctask(shutdown, events[0], events[1]),
            loop=async_loop
        )
        print(f"asynctask launched: {asynctask_future}", file=sys.stderr)

    timer_thread = None
    if True:
        timer_thread = Thread(target=timerthread, args=(shutdown, events[0], events[1]), daemon=True)
        timer_thread.start()

    if True:
        # Loop wait with timeouts on its private interrupt until shutdownEvent is set.
        try:
            interruptEvent2 = Event()
            for i in range(5):
                print('__main__ -------------------------')
                print(f"__main__[{i}] waiting", file=sys.stderr)
                result = shutdown.wait(interruptEvent2, timeout=10)
                interruptEvent2.clear()
                #print(f"__main__[{i}] wait result: {result}", file=sys.stderr)

                if interruptEvent2.is_set():
                    #print('__main__[{i}] interrupted ...', file=sys.stderr)
                    interruptEvent2.clear()

                if shutdown.is_set():
                    print(f"__main__[{i}] shutdown", file=sys.stderr)
                    break

        except Exception as e:
            print(f"Exception in main loop: {e}", file=sys.stderr)
            traceback.print_exc()
            exit(1)

        print(f"__main__[{i}] loop exited, finished doing shutdown", file=sys.stderr)
    shutdown.set()
    print(f"__main__[{i}] shutdown event set, waiting for timer thread to finish", file=sys.stderr)
    if timer_thread:
        timer_thread.join()
    print(f"__main__[{i}] shutdown event set, finished", file=sys.stderr)

    # Stop the asyncio loop and wait for thread to finish
    if asyncio_future:
        async_loop.call_soon_threadsafe(async_loop.stop)
        asyncio_thread.join()
        print(f"__main__[{i}] shutdown complete", file=sys.stderr)

    logger.info("Shutdown complete, exiting...")
    asycman.shutdown(timeout=5)



