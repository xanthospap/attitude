# -*- coding: utf-8 -*-

"""
downloader.py

Given a date (the_date),
download the attitude information (body quaternions and/or solar panel rotation angles)
for the "extended" week (9 days; Saturday to next Sunday).
"""

import argparse
import logging
import datetime

from prepattitude.configuration import SATELLITE_INFO
from prepattitude.date_calculator import DateCalculator
from prepattitude.basedownl.cddis_downloader import CDDISDownloader
from prepattitude.basedownl.copernicus_downloader import CopernicusDownloader
from prepattitude.basedownl.ign_downloader import IgnFtpDownloader


# LOGGING_LEVEL = logging.INFO
LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)
logger = logging.getLogger(__name__)


def extended_interval(t, add_days_before=2, add_days_after=3):
    t = (
        datetime.datetime.combine(t, datetime.datetime.min.time())
        if isinstance(t, datetime.date)
        else t
    )
    return t - datetime.timedelta(days=add_days_before), t + datetime.timedelta(
        days=add_days_after
    )


def download_data(satellite: str, the_date: str, save_dir: str, **kwargs) -> list[str]:
    """Construct a Downloader object and download data.
    Returns the list of daownloaded files (i.e. local files, including path).
    """
    tstart, tstop = extended_interval(the_date)

    logger.info(
        f"""\
Downloading quaternions for the "extended" week around {the_date} for satellite {satellite}.\
        """
    )

    match satellite:
        case "ja1" | "ja2" | "ja3":
            downloader = CDDISDownloader(satellite, **kwargs)
        case "s3a" | "s3b" | "s6a":
            downloader = CopernicusDownloader(satellite, **kwargs)
        case "swo":
            downloader = IgnFtpDownloader(satellite, **kwargs)

    return downloader.download_data(tstart, tstop, save_dir)
