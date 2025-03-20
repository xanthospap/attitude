# -*- coding: utf-8 -*-

"""attitude.py

Download and preprocess quaternion files:
    - detect and remove outliers
    - detect non-normalized quaternions (discard or fix)
    - interpolate quaternions (using SLERP) and rotation angles
"""

import argparse
import logging

# from configuration import SATELLITE, SAVE_DIR
from downloader import download_data
from preprocess import preprocess


# LOGGING_LEVEL = logging.INFO
LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style='{',
    format='{levelname}: {name} ({funcName}) [{lineno}]:  {message}'
)
logger = logging.getLogger(__name__)

def _parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="qpreprocess.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Given a string that represents a date,
download the attitude information (body quaternions and/or solar panel rotation angles)
for the "extended" week (9 days; Saturday to next Sunday) and preprocess the quaternions data.""",
    )
    parser.add_argument(
        "the_date",
        help="""A string that represents the date for which the quaternions are needed.
It should be in ISO format (YYYY-MM-DD)."""
)
    args = parser.parse_args()
    return args

# run
if __name__ == '__main__':
    args = _parse_arguments()
    download_data(args.the_date)
    preprocess()
