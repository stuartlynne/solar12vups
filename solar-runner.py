#!/usr/bin/env python3
# -*- coding: utf-8 -*-


"""Convenience wrapper for running bootstrap directly from source tree."""


import logging
from lib.log import setup_logger, xreport
if __name__ == '__main__':
    logger = setup_logger()
    pass
#else:                                     
logger = logging.getLogger(__name__)
logger.info("Solar12VUPS LOGGER TEST")


from app.solar12vups import SolarMain

if __name__ == '__main__':
    SolarMain()
