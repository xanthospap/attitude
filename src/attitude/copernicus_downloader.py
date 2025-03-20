# -*- coding: utf-8 -*-

"""
copernicus_downloader.py

Given a date (the_date),
download the attitude information (body quaternions)
for the "extended" week (9 days; Saturday to next Sunday).
"""

import datetime
import logging
import pathlib

import boto3

from configuration import SATELLITE, BASE_URL, SAVE_DIR

LOGGING_LEVEL = logging.INFO
# LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

# TODO: Fix this is a hack!
# Module `botocore` is giving log mesages at INFO level about skipping checksum validation,
# but this info is missing from the files in the Copernicus repository.
logging.getLogger('botocore').setLevel(logging.WARNING)

logging.basicConfig(
    level=LOGGING_LEVEL,
    style='{',
    format='{levelname}: {name} ({funcName}) [{lineno}]:  {message}',
)


class CopernicusDownloader:
    """Downloader object."""

    def __init__(self, satellite: str = SATELLITE, base_url: str = BASE_URL) -> None:
        self._satellite = satellite
        self._base_url = base_url
        self._logger = logging.getLogger(self.__class__.__name__)

        # parse configuration
        _cfg = {}
        with open('.s3cfg') as fh:
            for line in fh:
                try:
                    key, value = line.split('=')
                    _cfg[key.strip()] = value.strip()
                except ValueError:
                    # this is for header lines, e.g. [default]
                    pass

        # initialize & configure session and bucket
        _session = boto3.session.Session()
        _s3 = boto3.resource(
            's3',
            endpoint_url=f"https://{_cfg['host_base']}",
            aws_access_key_id=_cfg['access_key'],
            aws_secret_access_key=_cfg['secret_key'],
            region_name='default'
        )  # generated secrets
        self._bucket = _s3.Bucket("eodata")


    def _generate_products(self, date_ranges: list[list[datetime.date]]) -> list[str]:
        """Generate the product URL for each sublist of the given date ranges."""
        products = []
        for dr in date_ranges:
            products += [f'{self._base_url}/{d.year:4d}/{d.month:02d}/{d.day:02d}/' for d in dr]

        self._logger.debug(products)
        return products

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

    def _download_product(self, product: str, target: str = "") -> None:
        """
        Downloads every file in bucket with provided product as prefix.
        Raises FileNotFoundError if the product was not found.
        Args:
            product: Path to product
            target: Local catalog for downloaded files. Should NOT end with an `/`.
                Default current directory.
        """
        files = self._bucket.objects.filter(Prefix=product)
        if not list(files):
            self._logger.error(f"ERROR! Could not find any files for {product}.")
            raise FileNotFoundError
        for file in files:
            if not pathlib.Path(file.key).is_dir():
                qfile = f"{target}/{file.key.split('/')[-1]}"
                self._bucket.download_file(file.key, qfile)
                return qfile

    def download_data(
        self,
        date_ranges: list[list[datetime.date]],
        save_dir: str = SAVE_DIR,
        data_type: str = None,
    ) -> None:
        """Download data for the given date and save it to the specified directory."""
        self._make_save_dir(save_dir)

        for product in self._generate_products(date_ranges):
            try:
                qfile = self._download_product(product, save_dir)
                self._logger.info(f"Data downloaded and saved to {qfile}.")
            except:  # noqa: E722
                self._logger.error(f"Failed to download product {product}")
