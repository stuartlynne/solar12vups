
import sys
import asyncio
import signal
from time import time, sleep
from enum import Enum
from threading import Thread, Event
import traceback

import logging
from lib.log import setup_logger, xreport

from lib.shutdown import Shutdown
from lib.asyncman import AsyncTaskManager

if __name__ == '__main__':
    logger = setup_logger()
else:                                     
    logger = logging.getLogger(__name__)
                    
logger.info("AEvennts LOGGER TEST")

class AEvents:
    """
    AEvents extends asyncio events.

    Provide a way for tasks to:
        - wait for an event to be set
        - terminated after a timeout
        - be interrupted by the SIGINT signal
        - be shutdown by the SIGINT signal
        - sleep that can be interrupted for shutdown
    """

    class EventStatus(Enum):
        NONE = 0            # No status
        WAITING = 1         # Waiting for an event
        SET = 2             # Event was set
        TIMEOUT = 3         # Event timed out
        TASKSET = 4         # Task was set
        INTERRUPTED = 5     # Interrupted
        SHUTDOWN = 6        # Shutdown    

    def __init__(self, shutdown, ):
        logger.info('AEvents.__init__ ...')
        self.name = 'AEvents'

        #self.loop = asyncio.get_event_loop()
        self.loop = None

        #self.sigintEvent, self.shutdownEvent = events

        self.shutdown = shutdown
        self.events = self.shutdown.events()
        self.sigintEvent, self.shutdownEvent = self.events
        for event in self.events:
            event.clear()

        self.all_events = {}
        self.shutdown_events = []
        self.interrupt_events = []
        self.task_events = []
        self.sleeping = {}
        self.last_event = {}

        self._timer_thread = None


    def is_shutdown(self):
        return self.shutdownEvent.is_set() 

    def start(self):
        logger.info('AEvents.start ...')

        try:
            if self.loop is None:
                self.loop = asyncio.get_event_loop()

            self._timer_thread = Thread(target=self.aevents_timerthread, args=(self.shutdown, self.sigintEvent, self.shutdownEvent), daemon=True)
            self._timer_thread.start()
        except Exception as e:
            logger.info(f"Exception in AEvents start: {e}")
            logger.info(traceback.format_exc())


    # timer thread waits with short timeout on the sigint event.
    # When not shutdown, it checks the sleeping events and sets the event they are waiting on.
    def aevents_timerthread(self, shutdown, sigintEvent, shutdownEvent):

        #logger.info('-------------------------')
        interruptEvent1 = Event()
        while not shutdownEvent.is_set():
            shutdown.wait(interruptEvent1, timeout=3)
            interruptEvent1.clear()
            logger.debug('-------------------------')
            logger.debug(f'aevents_timerthread: running sigint {sigintEvent.is_set()} shutdown ({shutdownEvent.is_set()}) ...')
            logger.debug(f"aevents_timerthread: interrupt_events {self.interrupt_events}")
            if sigintEvent.is_set():
                sigintEvent.clear()
                for name in self.interrupt_events:
                    #xreport('AEvents.aevents_timerthread', f'{name} interrupted', yellow=True, )
                    if name in self.all_events:
                        self.set(name, status=self.EventStatus.INTERRUPTED)

            to_clear = []
            logger.debug('aevents_timerthread: sleeping %s ...' % (self.sleeping, ))
            for name, (start_time, timeout) in [v for v in self.sleeping.items()]:
                logger.debug(f"aevents_timerthread: {name} {start_time+timeout:.0f} {time():.0f}")
                if time() - start_time > timeout:
                    #xreport('AEvents.aevents_timerthread', f'{name} timeout', yellow=True, )
                    if name in self.all_events:
                        self.set(name, status=self.EventStatus.TIMEOUT)
                    to_clear.append(name)
            for name in to_clear:
                del self.sleeping[name]

        logger.debug('aevents_timerthread: timer thread shutdown ... AAAA')
        for name in self.shutdown_events:
            if name in self.all_events:
                self.set(name, status=self.EventStatus.SHUTDOWN)
        logger.debug('aevents_timerthread: timer thread shutdown ... BBBB')


    def stop(self,):
        logger.info('stop ...')
        #self._sigintEvent.set()
        # Cancel and await the timer task
        if self._timer_thread:
            if self._timer_thread.is_alive():
                self._timer_thread.join()

    def clear(self, name):
        if name in self.all_events:
            self.all_events[name].clear()
        if name in self.last_event:
            del self.last_event[name]

    def set(self, name, status=None, msg=''):
        #logger.info(f'set {name} {status} {msg}')
        if status is None:
            status = self.EventStatus.SET
        if name in self.all_events:
            self.last_event[name] = status
            self.loop.call_soon_threadsafe(self.all_events[name].set)

    def status(self, name):
        return self.last_event.get(name, self.EventStatus.NONE)

    def is_set(self, name):
        if name in self.all_events:
            return self.all_events[name].is_set()
        return False

    # Wait on a named event allowing for termination when:
    #   - the event to be set
    #   - optionally timeout 
    #   - optionally Interrupt signal (business logic specific, generally restart the task logic)
    #   - optionally Shutdown signal cleanly shut down the task and exit
    #
    # If autoClear is True, the event will be cleared after waiting.
    #
    async def wait(self, eventName=None, shutdownFlag=True, interruptFlag=True, taskFlag=False, timeout=None, autoClear=True):

        if eventName not in self.all_events:
            #xreport('AEvents.wait', f'{eventName} creating with shutdownFlag={shutdownFlag}, interruptFlag={interruptFlag}, taskFlag={taskFlag}, timeout={timeout}, autoClear={autoClear}')
            event = asyncio.Event()
            event.clear()
            self.all_events[eventName] = event
            if shutdownFlag: self.shutdown_events.append(eventName)
            if interruptFlag: self.interrupt_events.append(eventName)
            if taskFlag: self.task_events.append(eventName)
        #else:
        #    xreport('AEvents.wait', f'{eventName} timeout={timeout}, autoClear={autoClear}', yellow=True,)

        if timeout is not None:
            self.sleeping[eventName] = (time(), timeout)
            #xreport('AEvents.wait', f'{eventName} sleeping {self.sleeping[eventName]}', yellow=True,)

        self.last_event[eventName] = self.EventStatus.WAITING
        event = self.all_events[eventName]
        #xreport('AEvents.wait', f'{eventName} wait with timeout {timeout}', yellow=True,)
        result = await event.wait()
        #xreport('AEvents.wait', f'{eventName} wait result: {result}, status: {self.last_event[eventName]}', yellow=True,)
        if autoClear:
            event.clear()
        #self.sleeping.pop(eventName, None)
        return result, self.last_event.get(eventName, self.EventStatus.NONE)
# #######################################################################3



# async task to do wait with timeouts on its private interrupt until shutdownEvent is set.
async def asynctask(shutdown, sigintEvent, shutdownEvent):
    try:
        asyncEvent1 = asyncio.Event()
        while not shutdownEvent.is_set():
            shutdown.wait(asyncEvent1, timeout=3)
            asyncEvent1.clear()
            logger.info('asynctask -------------------------')
            logger.info(f'asynctask waiting sigint {sigintEvent.is_set()} shutdown ({shutdownEvent.is_set()}) ...')
            if sigintEvent.is_set():
                sigintEvent.clear()
                logger.info('asynctask interrupted ...')
                asyncEvent1.set()
    except Exception as e:
        logger.info(f"Exception in asynctask: {e}")
        logger.info(traceback.format_exc())
        return

# Timer thread to do wait with timeouts on its private interrupt until shutdownEvent is set.
def test_timerthread(shutdown, sigintEvent, shutdownEvent):

    logger.info(f"test_timerthread started with sigintEvent: {sigintEvent} shutdownEvent: {shutdownEvent}")
    try:
        interruptEvent1 = Event()

        while not shutdownEvent.is_set():
            shutdown.wait(interruptEvent1, timeout=3)
            interruptEvent1.clear()
            logger.info('test_timerthread -------------------------')
            logger.info(f'test_timerthread running sigint {sigintEvent.is_set()} interrupt ({interruptEvent1.is_set()}) shutdown ({shutdownEvent.is_set()}) ...')
            if interruptEvent1.is_set():
                interruptEvent1.clear()
                logger.info('test_timerthread interrupted ...')

    except Exception as e:
        logger.info(f"Exception in test_timerthread: {e}")
        logger.info(traceback.format_exc())

    logger.info('test_timerthread shutdown ... AAAA')

async def xtest_wait(aevents=None):

    aevents.start()
    try:
        while True:
            #aevents.Event('test_event', interruptFlag=True, stopFlag=True)
            #logger.info('test_event created')

            logger.info('0. test_event wait -------------------')
            results = await aevents.wait('test_event', timeout=4)
            logger.info(f'0. test_event wait result: {results}')
            logger.info('0. test_event waited again')
            if results[1] == aevents.EventStatus.SHUTDOWN: break

            logger.info('1. test_event wait timeout -----------')
            results = await aevents.wait(eventName='test_event', timeout=7)
            logger.info(f'1. test_event wait result: {results}')
            logger.info('1. test_event waited (should timeout or auto-set by timer)')
            if results[1] == aevents.EventStatus.SHUTDOWN: break

            logger.info('2. test_event wait -------------------')
            results = await aevents.wait('test_event')
            logger.info(f'2. test_event wait result: {results}')
            logger.info('2. test_event waited again')
            if results[1] == aevents.EventStatus.SHUTDOWN: break

            logger.info()
            logger.info('3. test_event wait timeout -----------')
            results = await aevents.wait(eventName='test_event', timeout=7)
            logger.info(f'3. test_event wait result: {results}')
            logger.info('3. test_event waited (should timeout or auto-set by timer)')
            if results[1] == aevents.EventStatus.SHUTDOWN: break


            logger.info()
            logger.info('4. test_event wait -------------------')
            results = await aevents.wait('test_event')
            logger.info(f'4. test_event wait result: {results}')
            logger.info('4. test_event waited again')
            if results[1] == aevents.EventStatus.SHUTDOWN: break

    except Exception as e:
        logger.exception(f'Exception: {e}')

    finally:
        logger.info('Cleaning up ...')
        aevents.stop()

    logger.info('Test completed')

# 
def xmainthread(shutdown, sigintEvent, shutdownEvent):
    logger.info('mainthread started')
    asyncman = AsyncTaskManager()
    asyncman.start()
    aevents = AEvents(shutdown, )

    if True:
        # Launch asyncio task
        asyncman.run(test_wait(aevents))

    if False:
        # Launch asyncio task
        asyncman.run(asynctask(events[0], events[1]))

    asyncio_future = None
    if False:
        # Launch asyncio loop in a separate thread
        async_loop = asyncio.new_event_loop()
        asyncio_thread = Thread(target=async_loop.run_forever, daemon=True)
        asyncio_thread.start()
        # Submit coroutine to the async loop
        asyncio_future = asyncio.run_coroutine_threadsafe(
            asynctask(events[0], events[1]),
            loop=async_loop
        )
        logger.info(f"asynctask launched: {asynctask_future}")

    timer_thread = None
    if False:
        timer_thread = Thread(target=test_timerthread, args=(events[0], events[1]), daemon=True)
        timer_thread.start()

    if True:
        # Loop wait with timeouts on its private interrupt until shutdownEvent is set.
        try:
            interruptEvent2 = Event()
            for i in range(5):
                logger.info('__main__ -------------------------')
                logger.info(f"__main__[{i}] waiting")
                result = shutdown.wait(interruptEvent2, timeout=10)
                #logger.info(f"__main__[{i}] wait result: {result}")

                if interruptEvent2.is_set():
                    #logger.info('__main__[{i}] interrupted ...')
                    interruptEvent2.clear()

                if shutdown.is_set():
                    logger.info(f"__main__[{i}] shutdown")
                    break

                logger.info(f"__main__[{i}] loop exited, finished doing shutdown")

        except Exception as e:
            logger.exception(f"Exception in main loop: {e}")

    shutdown.set()
    logger.info(f"__main__[{i}] shutdown event set, waiting for timer thread to finish")
    if timer_thread:
        timer_thread.join()
    logger.info(f"__main__[{i}] shutdown event set, finished")

    # Stop the asyncio loop and wait for thread to finish
    if asyncio_future:
        async_loop.call_soon_threadsafe(async_loop.stop)
        asyncio_thread.join()
        logger.info(f"__main__[{i}] shutdown complete")

    asyncman.shutdown(timeout=5)

if __name__ == '__main__':

    #setup_logger('shutdown')
    #logger = logging.getLogger(__name__).info("Starting aevents example")


    shutdown = Shutdown()
    events = shutdown.events()
    sigintEvent, shutdownEvent = events
    main_thread = Thread(target=mainthread, args=(shutdown, events[0], events[1]), daemon=True)
    main_thread.start()

    # Loop wait with timeouts on its private interrupt until shutdownEvent is set.
    mainEvent1 = Event()
    try:
        result = shutdown.wait(mainEvent1, timeout=10)
        mainEvent1.clear()

    except Exception as e:
        logger.exception(f"Exception in main loop: {e}")
        exit(1)

    logger.info(f"__main__ shutdown event set, waiting for timer thread to finish")
    if main_thread:
        main_thread.join()
    logger.info(f"__main__ shutdown event set, finished")

