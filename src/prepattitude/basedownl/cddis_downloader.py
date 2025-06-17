# -*- coding: utf-8 -*-

"""
cddis_downloader.py

Given a date (the_date),
download the attitude information (body quaternions & solar panel rotation angles)
for the "extended" week (9 days; Saturday to next Sunday).
"""

import datetime
import logging
import multiprocessing
import pathlib
import requests
import re
from opnieuw import retry
from os.path import exists, basename

from prepattitude.configuration import SATELLITE_INFO

LOGGING_LEVEL = logging.INFO
# LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)


def ja_product_range(satellite, fn):
    fn = basename(fn)
    if fn.startswith(f"{satellite}qsolp"):
        match = re.match(r"ja?qsolp(\d{14})_(\d{14})\.\d{3}", fn)
        if match:
            start_str, end_str = match.groups()
            start_dt = datetime.strptime(start_str, "%Y%m%d%H%M%S")
            end_dt = datetime.strptime(end_str, "%Y%m%d%H%M%S")
            return start_dt, end_dt
    elif fn.startswith(f"{satellite}qbody"):
        match = re.match(r"ja?qbody(\d{14})_(\d{14})\.\d{3}", fn)
        if match:
            start_str, end_str = match.groups()
            start_dt = datetime.strptime(start_str, "%Y%m%d%H%M%S")
            end_dt = datetime.strptime(end_str, "%Y%m%d%H%M%S")
            return start_dt, end_dt
    return None


class CDDISDownloader:
    """Downloader object."""

    def __init__(self, satellite: str, **kwargs) -> None:
        self._satellite = satellite
        self._base_url = SATELLITE_INFO[satellite]["base_url"]
        self._logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    @retry(
        retry_on_exceptions=(
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ),
        max_calls_total=4,
        retry_window_after_first_call_in_seconds=60,
    )
    def _get_directory_listing(url: str) -> str:
        """List the files on the server directory."""
        # add the required suffix and make the request
        response = requests.get(f"{url}/*?list")
        response.raise_for_status()  # raise an exception for bad requests

        return response.text

    def _generate_urls(self, start_t, end_t) -> list[str]:
        """Generate the URL of the given data type, for each sublist of the given date ranges."""
        dates = [
            start_t + datetime.timedelta(days=i) for i in range((end_t - start_t).days)
        ]
        urls = []
        crp = -1
        for t in dates:
            url = f"{self._base_url}/{self._satellite}/{t.year}"
            if t.year != crp:
                listing = self._get_directory_listing(url).split("\n")[:-1]
                crp = t.year
            for fn in listing:
                t0, t1 = ja_product_range(self._satellite, fn)
                if t0 < end_t and start_t < t1:
                    urls.append(url)
        self._logger.debug(urls)
        return urls

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

    @retry(
        retry_on_exceptions=(
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ),
        max_calls_total=4,
        retry_window_after_first_call_in_seconds=60,
    )
    def _get_data(
        self, url: str, chunk_size: int, queue: multiprocessing.Queue
    ) -> None:
        """Download data from the given URL in chunks and put them into a queue."""
        response = requests.get(url, stream=True)
        response.raise_for_status()  # raise an exception for bad requests

        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:  # filter out keep-alive new chunks
                queue.put(chunk)

        # indicate that downloading is done
        queue.put(None)

    def _write_data(
        self, file_path: pathlib.Path, queue: multiprocessing.Queue
    ) -> None:
        """Write data chunks from the queue to a file."""
        with open(file_path, "wb") as fh:
            while True:
                chunk = queue.get()
                if chunk is None:
                    break
                fh.write(chunk)

    def _download_file(
        self, url: str, file_path: pathlib.Path, chunk_size: int = 1000
    ) -> None:
        """Coordinate the downloading and writing of a file using subprocesses."""
        queue = multiprocessing.Queue()

        # create and start subprocesses
        download_process = multiprocessing.Process(
            target=self._get_data, args=(url, chunk_size, queue)
        )
        download_process.start()
        write_process = multiprocessing.Process(
            target=self._write_data, args=(file_path, queue)
        )
        write_process.start()

        # wait for subprocesses to finish
        download_process.join()
        write_process.join()

    def download_data(self, start_t, end_t, save_dir: str) -> list[str]:
        """Download data for the given date and save it to the specified directory.
        Returns the list of files downloaded (path + filename).
        """
        self._make_save_dir(save_dir)
        downloaded_files = []

        for url in self._generate_urls(start_t, end_t):
            # infer local filename
            qfile = pathlib.Path(save_dir, url.split("/")[-1])
            try:
                self._logger.debug(
                    f"Trying to download remote file {url} to local file {qfile}."
                )
                # only download if file not already present
                if not exists(qfile):
                    self._download_file(url, qfile, 1000)
                downloaded_files.append(qfile)
                self._logger.info(f"Data downloaded and saved to {qfile}.")
            except requests.exceptions.RequestException:
                self._logger.error(f"Failed to download file {url}")
        return downloaded_files
