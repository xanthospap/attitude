# -*- coding: utf-8 -*-

"""
downloader.py

Given a date (the_date),
download the attitude information (body quaternions and/or solar panel rotation angles)
for the "extended" week (9 days; Saturday to next Sunday).
"""

import argparse
import logging

from prepattitude.configuration import SATELLITE_INFO
from prepattitude.date_calculator import DateCalculator
from prepattitude.basedownl.cddis_downloader import CDDISDownloader
from prepattitude.basedownl.copernicus_downloader import CopernicusDownloader


# LOGGING_LEVEL = logging.INFO
LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)
logger = logging.getLogger(__name__)


def download_data(satellite: str, the_date: str, save_dir: str) -> list[str]:
    """Construct a Downloader object and download data.
    Returns the list of daownloaded files (i.e. local files, including path).
    """
    dranges = DateCalculator(the_date).date_ranges
    logger.debug(dranges)

    logger.info(
        f"""\
Downloading quaternions for the "extended" week around {the_date} for satellite {satellite}.\
        """
    )

    match satellite:
        case "ja1" | "ja2" | "ja3":
            downloader = CDDISDownloader(
                satellite, SATELLITE_INFO[satellite]["base_url"]
            )
        case "s3a" | "s3b" | "s6a":
            downloader = CopernicusDownloader(
                satellite, SATELLITE_INFO[satellite]["base_url"]
            )

    localq = []
    for data_type in SATELLITE_INFO[satellite]["data_types"]:
        localq += downloader.download_data(dranges, save_dir, data_type)

    return localq
