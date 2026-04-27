from __future__ import annotations

import datetime as dt
import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


logger = logging.getLogger(__name__)


VMF_BASE_URL = "https://vmf.geo.tuwien.ac.at/trop_products/GRID"

SUPPORTED_TYPES = {
    "v3gr": {
        "path": "V3GR/V3GR_OP",
        "filename_prefix": "V3GR",
    },
}


def floor_to_6h(epoch: dt.datetime) -> dt.datetime:
    hour = (epoch.hour // 6) * 6

    return epoch.replace(
        hour=hour,
        minute=0,
        second=0,
        microsecond=0,
    )


def ceil_to_6h(epoch: dt.datetime) -> dt.datetime:
    floored = floor_to_6h(epoch)

    if floored == epoch:
        return epoch

    return floored + dt.timedelta(hours=6)


def vmf_epochs_for_range(
    start: dt.datetime,
    end: dt.datetime,
) -> list[dt.datetime]:
    """
    Return all 6-hour VMF epochs needed to cover [start, end).

    Includes the first epoch at or after `end`, so a full day produces:

        00, 06, 12, 18, next-day 00
    """

    if end <= start:
        raise ValueError("End datetime must be after start datetime")

    first = floor_to_6h(start)
    last = ceil_to_6h(end)

    epochs: list[dt.datetime] = []
    current = first

    while current <= last:
        epochs.append(current)
        current += dt.timedelta(hours=6)

    return epochs


def vmf_filename(
    epoch: dt.datetime,
    product_type: str = "v3gr",
) -> str:
    product_type = product_type.lower()

    if product_type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported VMF product type: {product_type}")

    prefix = SUPPORTED_TYPES[product_type]["filename_prefix"]

    return f"{prefix}_{epoch:%Y%m%d}.H{epoch:%H}"


def vmf_url(
    epoch: dt.datetime,
    product_type: str = "v3gr",
    grid: str = "5x5",
    base_url: str = VMF_BASE_URL,
) -> str:
    product_type = product_type.lower()

    if product_type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported VMF product type: {product_type}")

    if grid not in {"1x1", "5x5"}:
        raise ValueError(f"Unsupported VMF grid: {grid}")

    product_path = SUPPORTED_TYPES[product_type]["path"]
    filename = vmf_filename(epoch, product_type=product_type)

    return (
        f"{base_url.rstrip('/')}/"
        f"{grid}/"
        f"{product_path}/"
        f"{epoch.year:04d}/"
        f"{filename}"
    )


def vmf_urls_for_range(
    start: dt.datetime,
    end: dt.datetime,
    product_type: str = "v3gr",
    grid: str = "5x5",
) -> list[str]:
    return [
        vmf_url(
            epoch=epoch,
            product_type=product_type,
            grid=grid,
        )
        for epoch in vmf_epochs_for_range(start, end)
    ]


def filename_from_url(url: str) -> str:
    filename = Path(urlparse(url).path).name

    if not filename:
        raise ValueError(f"Could not infer filename from URL: {url}")

    return filename


def download_url(
    url: str,
    output_dir: str | Path,
    overwrite: bool = False,
    timeout: float = 60.0,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / filename_from_url(url)

    if output_file.exists() and not overwrite:
        logger.info("Using existing file %s", output_file)
        return output_file

    tmp_file = output_file.with_suffix(output_file.suffix + ".part")

    logger.info("Downloading %s", url)

    with urlopen(url, timeout=timeout) as response:
        with tmp_file.open("wb") as fout:
            shutil.copyfileobj(response, fout)

    tmp_file.replace(output_file)

    return output_file


def download_vmf(
    start: dt.datetime,
    end: dt.datetime,
    output_dir: str | Path,
    product_type: str = "v3gr",
    grid: str = "5x5",
    overwrite: bool = False,
) -> list[Path]:
    urls = vmf_urls_for_range(
        start=start,
        end=end,
        product_type=product_type,
        grid=grid,
    )

    files: list[Path] = []

    for url in urls:
        try:
            files.append(
                download_url(
                    url=url,
                    output_dir=output_dir,
                    overwrite=overwrite,
                )
            )
        except Exception as exc:
            logger.error("Failed to download %s: %s", url, exc)

    return files
