from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

from sources.vmf import SUPPORTED_TYPES, download_vmf


logger = logging.getLogger(__name__)


def parse_datetime(value: str) -> dt.datetime:
    """
    Accept:
        2024-01-02
        2024-01-02T12:30:00
        2024-01-02 12:30:00
    """

    value = value.strip().replace("Z", "")

    try:
        return dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid datetime {value!r}. " "Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vmfdwn",
        description="Download VMF products.",
    )

    parser.add_argument(
        "-b",
        "--begin",
        required=True,
        type=parse_datetime,
        metavar="DATETIME",
        help="Start datetime, e.g. 2024-01-02 or 2024-01-02T12:00:00.",
    )

    parser.add_argument(
        "-e",
        "--end",
        required=True,
        type=parse_datetime,
        metavar="DATETIME",
        help="End datetime, e.g. 2024-01-03 or 2024-01-03T12:00:00.",
    )

    parser.add_argument(
        "-d",
        "--save-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory where VMF files are saved.",
    )

    parser.add_argument(
        "--type",
        default="v3gr",
        choices=sorted(SUPPORTED_TYPES),
        help="VMF product type. Default: v3gr.",
    )

    parser.add_argument(
        "--grid",
        default="5x5",
        choices=["1x1", "5x5"],
        help="VMF grid resolution. Default: 5x5.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Download again even if the local file already exists.",
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

    files = download_vmf(
        start=args.begin,
        end=args.end,
        output_dir=args.save_dir,
        product_type=args.type,
        grid=args.grid,
        overwrite=args.overwrite,
    )

    if not files:
        raise SystemExit("ERROR: no VMF files were downloaded.")

    for file in files:
        print(file)


if __name__ == "__main__":
    main()
