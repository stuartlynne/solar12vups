import sys
import argparse
from lib.log import setup_logger
from app.solar12vups import SolarMain

def main():
    parser = argparse.ArgumentParser(description="Solar12VUPS runner")
    parser.add_argument("--stderr", action="store_true", help="Enable console logging to stderr")
    args = parser.parse_args()

    setup_logger(stderr=args.stderr)
    SolarMain()

if __name__ == "__main__":
    main()
