# -*- coding: utf-8 -*-

"""
downloader.py

Given a date (the_date),
download the attitude information (body quaternions and/or solar panel rotation angles)
for the "extended" week (9 days; Saturday to next Sunday).
"""

import argparse
import logging

from configuration import SATELLITE, SAT_NAME, BASE_URL, SAVE_DIR, DATA_TYPES
from date_calculator import DateCalculator
from cddis_downloader import CDDISDownloader
from copernicus_downloader import CopernicusDownloader


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
        prog="downloader.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Given a string that represents a date,
download the attitude information (body quaternions and/or solar panel rotation angles)
for the "extended" week (9 days; Saturday to next Sunday).""",
    )
    parser.add_argument(
        "the_date",
        help="""A string that represents the date for which the quaternions are needed.
It should be in ISO format (YYYY-MM-DD)."""
)
    args = parser.parse_args()
    return args

def download_data(the_date: str) -> None:
    """Construct a Downloader object and download data."""
    dranges = DateCalculator(the_date).date_ranges
    logger.debug(dranges)

    logger.info(
        f"""\
Downloading quaternions for the "extended" week around {the_date} for satellite {SAT_NAME}.\
        """
    )

    match SATELLITE:
        case 'ja3':
            downloader = CDDISDownloader(SATELLITE, BASE_URL)
        case 's3a' | 's3b' | 's6a':
            downloader = CopernicusDownloader(SATELLITE, BASE_URL)

    try:
        for data_type in DATA_TYPES:
            downloader.download_data(dranges, SAVE_DIR, data_type)
    except TypeError:
        downloader.download_data(dranges, SAVE_DIR)
    logger.debug(DATA_TYPES, SAVE_DIR)


if __name__ == '__main__':
    args = _parse_arguments()
    download_data(args.the_date)
