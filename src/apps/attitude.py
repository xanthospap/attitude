from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

from sources import cddis, copernicus
from sources.attitude import SATELLITE_INFO, product_overlaps_range
from preprocessors.attitude import preprocess_attitude

logger = logging.getLogger(__name__)


def parse_datetime(value: str) -> dt.datetime:
    """
    Accept:
        2024-01-01
        2024-01-01T12:30:00
        2024-01-01 12:30:00
    """

    value = value.strip().replace("Z", "")

    try:
        return dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid datetime {value!r}. " "Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
        ) from exc


def _keep_overlapping_files(
    files: list[str | Path],
    start: dt.datetime,
    end: dt.datetime,
) -> list[Path]:
    selected = [
        Path(file)
        for file in files
        if product_overlaps_range(Path(file).name, start, end)
    ]

    if not selected:
        logger.warning(
            "No downloaded products overlap requested range %s to %s",
            start,
            end,
        )

    return selected


def download_attitude_files(
    satellite: str,
    start,
    end,
    save_dir,
    overwrite: bool = False,
    s3cfg=None,
) -> list[Path]:
    satellite = satellite.lower()
    info = SATELLITE_INFO[satellite]

    if info["source"] == "cddis":
        return cddis.download_attitude(
            satellite=satellite,
            start=start,
            end=end,
            output_dir=save_dir,
            base_url=info["base_url"],
            data_types=info["data_types"],
            overwrite=overwrite,
        )

    if info["source"] == "copernicus":
        return copernicus.download_attitude(
            satellite=satellite,
            start=start,
            end=end,
            output_dir=save_dir,
            base_url=info["base_url"],
            overwrite=overwrite,
            s3cfg=s3cfg,
        )

    if info["source"] == "ign":
        raise NotImplementedError("SWOT/IGN source adapter is not migrated yet.")

    raise ValueError(f"Unsupported attitude source: {info['source']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepattitude",
        description=(
            "Download and preprocess satellite attitude files for a user-supplied "
            "datetime range."
        ),
    )

    parser.add_argument(
        "-b",
        "--begin",
        required=True,
        type=parse_datetime,
        metavar="DATETIME",
        help="Start datetime, e.g. 2024-01-01T00:00:00.",
    )

    parser.add_argument(
        "-e",
        "--end",
        required=True,
        type=parse_datetime,
        metavar="DATETIME",
        help="End datetime, e.g. 2024-01-03T00:00:00.",
    )

    parser.add_argument(
        "-s",
        "--satellite",
        required=True,
        choices=sorted(SATELLITE_INFO),
        help="Satellite identifier.",
    )

    parser.add_argument(
        "-d",
        "--save-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory where downloaded files are saved.",
    )

    parser.add_argument(
        "-n",
        "--every-sec",
        dest="nsec",
        default=5.0,
        type=float,
        help="Interpolation interval in seconds.",
    )

    parser.add_argument(
        "-p",
        "--password",
        default=None,
        help="Password for sources that require one.",
    )

    parser.add_argument(
        "--preprocess-only",
        nargs="+",
        type=Path,
        metavar="FILE",
        help="Skip downloading and preprocess the given local attitude files.",
    )

    parser.add_argument(
        "-o",
        "--output-file",
        type=Path,
        default=None,
        help="Output CSV file. Default: qua_<satellite>.csv beside the input files.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files even if they already exist locally.",
    )

    parser.add_argument(
        "--s3cfg",
        type=Path,
        default=None,
        help="Copernicus S3 config file. Default: ~/.s3cfg.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        style="{",
        format="{levelname}: {name} ({funcName}) [{lineno}]: {message}",
    )

    if args.end <= args.begin:
        raise SystemExit("ERROR: --end must be after --begin")

    if args.preprocess_only:
        files = _keep_overlapping_files(
            args.preprocess_only,
            args.begin,
            args.end,
        )
    else:
        files = download_attitude_files(
            satellite=args.satellite,
            start=args.begin,
            end=args.end,
            save_dir=args.save_dir,
            overwrite=args.overwrite,
            s3cfg=args.s3cfg,
        )

    output_file = preprocess_attitude(
        satellite=args.satellite,
        qfns=files,
        nsec=args.nsec,
        start=args.begin,
        end=args.end,
        output_file=args.output_file,
    )

    logger.info("Wrote %s", output_file)


if __name__ == "__main__":
    main()
