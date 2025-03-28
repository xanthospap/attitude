# -*- coding: utf-8 -*-

"""attitude.py

Download and preprocess quaternion files:
    - detect and remove outliers
    - detect non-normalized quaternions (discard or fix)
    - interpolate quaternions (using SLERP) and rotation angles
"""

import argparse
import logging
import datetime
from os import getcwd

from prepattitude.configuration import SATELLITE_INFO
from prepattitude.downloader import download_data
from prepattitude.preprocess import preprocess


# LOGGING_LEVEL = logging.INFO
LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(
    prog="qpreprocess.py",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description="""Given a string that represents a date,
download the attitude information (body quaternions and/or solar panel rotation angles)
for the "extended" week (9 days; Saturday to next Sunday) and preprocess the quaternions data.""",
)

parser.add_argument(
    "-e",
    "--date",
    type=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d"),
    metavar="DATE",
    dest="epoch",
    required=True,
    help="""A string that represents the date for which the quaternions are needed.
It should be in ISO format (YYYY-MM-DD).""",
)

parser.add_argument(
    "-d",
    "--save-dir",
    metavar="SAVE_DIR",
    dest="save_dir",
    required=False,
    default=getcwd(),
    help="Directory where attitude files are to be saved at.",
)

parser.add_argument(
    "-s",
    "--satellite",
    metavar="SATELLITE",
    required=True,
    dest="satellite",
    choices=["ja3", "s3a", "s3b", "s6a"],
    help="Sellect satellite.",
)


def main():
    args = args = parser.parse_args()
    preprocess(
        args.satellite, download_data(args.satellite, args.epoch.date(), args.save_dir)
    )
