# -*- coding: utf-8 -*-

""" """
from datetime import datetime, timedelta
import logging
import pathlib
import re
from ftplib import FTP
import numpy as np
from prepattitude.configuration import SATELLITE_INFO
from prepattitude.swot import swo_product_range

from os.path import join, isfile, basename

LOGGING_LEVEL = logging.INFO
# LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)


class IgnFtpDownloader:
    """Downloader object."""

    def __init__(self, satellite: str, **kwargs) -> None:
        self._satellite = satellite
        self._base_url = "doris.ign.fr"
        self._logger = logging.getLogger(self.__class__.__name__)
        self._username = "anonymous" if "username" not in kwargs else kwargs["username"]
        self._password = None if "password" not in kwargs else kwargs["password"]

    def download_data(self, start_t, end_t, save_dir: str) -> list[str]:
        """Download data for the given date and save it to the specified directory."""
        self._make_save_dir(save_dir)
        _ftp = FTP(self._base_url)
        _ftp.login(user=self._username, passwd=self._password)

        dates = [start_t + timedelta(days=i) for i in range((end_t - start_t).days)]

        urls = []
        crp = ""
        downloaded_files = []
        for t in dates:
            pth = join(SATELLITE_INFO[self._satellite]["base_url"], f"{t.year}")
            if pth != crp:
                _ftp.cwd(pth)
                listing = []
                _ftp.retrlines("LIST", listing.append)
                listing = [line.split()[-1] for line in listing]
                crp = pth
            for fn in listing:
                t0, t1 = swo_product_range(fn)
                if t0 < end_t and start_t < t1:
                    local_file = join(save_dir, fn)
                    if not isfile(local_file):
                        with open(local_file, "wb") as f:
                            _ftp.retrbinary(f"RETR {fn}", f.write)
                    downloaded_files.append(local_file)

        _ftp.quit()
        return downloaded_files

    def _make_save_dir(self, save_dir: str) -> None:
        """Make the directory to save the files."""
        try:
            pathlib.Path(save_dir).mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            self._logger.error(
                """ERROR!
A file with the same name as the given 'save_dir' already exists.
Please, select a different directory to save the files.
"""
            )
            raise
