#!/usr/bin/env python3
# -*- coding: utf-8 -*-


"""Convenience wrapper for running bootstrap directly from source tree."""

import sys
import logging
from lib.log import setup_logger, xreport


from app.solar12vups import SolarMain

def main():
    print('Solar12VUPS runner starting...', file=sys.stderr)
    logger = setup_logger()
    logger = logging.getLogger(__name__)
    logger.info("Solar12VUPS LOGGER TEST")
    SolarMain()

if __name__ == '__main__':
    main()
