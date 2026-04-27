from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from os.path import expanduser

import boto3

from sources.attitude import (
    dates_to_scan_for_range,
    product_overlaps_range,
)


logger = logging.getLogger(__name__)

# Avoid noisy checksum-validation messages from botocore.
logging.getLogger("botocore").setLevel(logging.WARNING)


def read_s3cfg(path: str | Path | None = None) -> dict[str, str]:
    """
    Read Copernicus S3 credentials from ~/.s3cfg by default.
    """

    if path is None:
        path = Path(expanduser("~")) / ".s3cfg"
    else:
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Missing Copernicus S3 config file: {path}")

    config: dict[str, str] = {}

    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()

            if not line or line.startswith("[") or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

    required = {"host_base", "access_key", "secret_key"}
    missing = required - set(config)

    if missing:
        raise KeyError(f"Missing required keys in {path}: {sorted(missing)}")

    return config


def eodata_bucket(s3cfg: str | Path | None = None):
    config = read_s3cfg(s3cfg)

    s3 = boto3.resource(
        "s3",
        endpoint_url=f"https://{config['host_base']}",
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name="default",
    )

    return s3.Bucket("eodata")


def satellite_token(satellite: str) -> str:
    tokens = {
        "s3a": "S3A",
        "s3b": "S3B",
        "s6a": "S6A",
    }

    satellite = satellite.lower()

    if satellite not in tokens:
        raise ValueError(f"Unsupported Copernicus attitude satellite: {satellite}")

    return tokens[satellite]


def attitude_day_prefix(
    base_url: str,
    date: dt.date,
) -> str:
    return f"{base_url.strip('/')}/{date.year:04d}/{date.month:02d}/{date.day:02d}/"


def find_attitude_keys(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    base_url: str,
    bucket=None,
) -> list[str]:
    """
    Find Copernicus S3 keys whose validity interval overlaps [start, end).
    """

    if bucket is None:
        bucket = eodata_bucket()

    token = satellite_token(satellite)
    keys: list[str] = []

    for date in dates_to_scan_for_range(start, end):
        prefix = attitude_day_prefix(base_url, date)

        for obj in bucket.objects.filter(Prefix=prefix):
            key = obj.key
            name = Path(key).name

            if not name:
                continue

            if not token in name.upper():
                continue

            if key.endswith("/"):
                continue

            if not product_overlaps_range(name, start, end):
                continue

            keys.append(key)

    return sorted(set(keys))


def download_key(
    key: str,
    output_dir: str | Path,
    bucket=None,
    overwrite: bool = False,
) -> Path:
    if bucket is None:
        bucket = eodata_bucket()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / Path(key).name

    if output_file.exists() and not overwrite:
        return output_file

    tmp_file = output_file.with_suffix(output_file.suffix + ".part")
    bucket.download_file(key, str(tmp_file))
    tmp_file.replace(output_file)

    return output_file


def download_attitude(
    satellite: str,
    start: dt.datetime,
    end: dt.datetime,
    output_dir: str | Path,
    base_url: str,
    overwrite: bool = False,
    s3cfg: str | Path | None = None,
) -> list[Path]:
    """
    Download Copernicus attitude files overlapping [start, end).
    """

    bucket = eodata_bucket(s3cfg=s3cfg)

    keys = find_attitude_keys(
        satellite=satellite,
        start=start,
        end=end,
        base_url=base_url,
        bucket=bucket,
    )

    files: list[Path] = []

    for key in keys:
        try:
            files.append(
                download_key(
                    key=key,
                    output_dir=output_dir,
                    bucket=bucket,
                    overwrite=overwrite,
                )
            )
        except Exception as exc:
            logger.error("Failed to download Copernicus key %s: %s", key, exc)

    return files
