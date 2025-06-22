import logging
import sys
import logging
from colored import stylize, fore, back, Style
from colored import stylize, fore, back, style
from lib.color256_enum import Color256

#print(stylize('Hello, World!', back('yellow')))
#print(stylize('This is green.', fore('green')))
#print('finished')



class ConsoleColorFormatter(logging.Formatter):
    def format(self, record):
        return getattr(record, 'colored_msg', record.getMessage())

from pathlib import Path
from shutil import move

def setup_logger():
    log_file = Path("/tmp/STDERR.txt")

    # Manually rotate if the main log exists
    if log_file.exists():
        for i in range(3, 0, -1):
            older = log_file.with_name(f"{log_file.name}.{i}")
            newer = log_file.with_name(f"{log_file.name}.{i + 1}")
            if older.exists():
                if newer.exists():
                    newer.unlink()
                move(older, newer)
        rolled = log_file.with_name(f"{log_file.name}.1")
        move(log_file, rolled)

    #logger = logging.getLogger('xreport')
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(ConsoleColorFormatter(fmt='%(message)s'))

    # File handler
    fh = logging.FileHandler(log_file, mode='w')  # Overwrite fresh each time
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(fmt='%(asctime)s %(levelname)s %(message)s'))

    logger.addHandler(ch)
    logger.addHandler(fh)

    return logger


def ansi_256_color(fg=None, bg=None):
    seq = ''
    if fg is not None:
        seq += f'\033[38;5;{fg}m'
    if bg is not None:
        seq += f'\033[48;5;{bg}m'
    return seq


def xreport(device_name, operation='', msg='', fore=Color256.BLACK, back=Color256.WHITE, 
            yellow=False, red=False, green=False, blue=False, grey=False, ):
    logger = logging.getLogger()
    if yellow:
        fore = Color256.BLACK
        back = Color256.LIGHT_YELLOW
    elif red:
        fore = Color256.BLACK
        back = Color256.INDIAN_RED_1C
    elif green:
        fore = Color256.BLACK
        back = Color256.LIGHT_GREEN
    elif blue:
        fore = Color256.BLACK
        back = Color256.LIGHT_CYAN
    elif grey:
        fore = Color256.BLACK
        back = Color256.LIGHT_GRAY

    formatted = f"[   {device_name:<20} {operation:>22}] {msg}"
    color_prefix = ansi_256_color(fg=fore.value, bg=back.value)
    color_suffix = '\033[0m'
    colored_formatted = f"{color_prefix}{formatted}{color_suffix}"

    # Attach raw and colored version to log record via `extra`
    logger.info(formatted, extra={'colored_msg': colored_formatted})

    #print(f"{color_prefix}{formatted}{color_suffix}", file=sys.stderr)
    #logger.log(logging.INFO, f"{color_prefix}{formatted}{color_suffix}")



if __name__ == '__main__':
    # Example usage
    logger = setup_logger()
    logger.info("Starting xreport example")
    xreport('Device1', 'Operation1', 'This is a test message', )
    xreport('Device1', 'Operation1', 'This is a test message', yellow=True) 
    xreport('Device1', 'Operation1', 'This is a test message', red=True) 
    xreport('Device1', 'Operation1', 'This is a test message', green=True) 
    xreport('Device1', 'Operation1', 'This is a test message', fore=Color256.RED, back=Color256.YELLOW)
    #xreport('Device2', 'Operation2', 'This is another test message', red=True)
    for back in Color256:
        xreport(back.value, back.name, f'This is a test message', back=back)
    
    logger.info("ending xreport example")
#logger = setup_logger()

# Then replace all print() calls like:
#logger.info("Starting shutdown system...")
#logger.warning("SIGINT received")
#logger.error("Unexpected shutdown")

