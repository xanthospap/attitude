# -*- coding: utf-8 -*-

import argparse
import logging
import datetime
from os import getcwd
import matplotlib.pyplot as plt

from cnesfr.parsemass import parse_cness_mass, plot_dmdg_variations


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
    description="",
)

parser.add_argument(
    "-b",
    "--begin-date",
    type=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d"),
    metavar="BEGIN_DATE",
    dest="begin_date",
    required=False,
    default=datetime.datetime.min,
    help="""A string that represents the begin date. It should be in ISO format (YYYY-MM-DD).""",
)
parser.add_argument(
    "-e",
    "--end-date",
    type=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d"),
    metavar="END_DATE",
    dest="end_date",
    required=False,
    default=datetime.datetime.max,
    help="""A string that represents the end date. It should be in ISO format (YYYY-MM-DD).""",
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
    "-m",
    "--mass-file",
    metavar="CNES_MASS_FILE",
    required=True,
    dest="mass_fn",
    help="Satellite mass file in CNES format.",
)


def main():
    args = args = parser.parse_args()
    data = parse_cness_mass(args.mass_fn, args.begin_date, args.end_date)
    fig, ax = plot_dmdg_variations(data)
    plt.show()
