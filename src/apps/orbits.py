from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

from sources import cddis, ign
from sources.orbits import DEFAULT_ANALYSIS_CENTER


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
        prog="sp3dwn",
        description="Download IDS DORIS SP3 orbit files.",
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
        "-s",
        "--satellite",
        required=True,
        metavar="SSS",
        help="3-character satellite ID, e.g. ja3, s3a, swo.",
    )

    parser.add_argument(
        "-d",
        "--save-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory where SP3 files are saved.",
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=["ign", "cddis"],
        help="Archive source.",
    )

    parser.add_argument(
        "-c",
        "--center",
        default=DEFAULT_ANALYSIS_CENTER,
        metavar="CCC",
        help="Analysis center, e.g. ssa, grg, gsc, lca. Default: ssa.",
    )

    parser.add_argument(
        "--version",
        default=None,
        metavar="VV",
        help="Optional two-digit product version filter.",
    )

    parser.add_argument(
        "-z",
        "--uncompress",
        action="store_true",
        help="Uncompress downloaded .Z files after downloading.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Download again even if the local file already exists.",
    )

    parser.add_argument(
        "--ftp-user",
        default="anonymous",
        help="FTP username for IGN. Default: anonymous.",
    )

    parser.add_argument(
        "--ftp-password",
        default="anonymous@",
        help="FTP password for IGN. Default: anonymous@.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    return parser


def download_sp3_files(args) -> list[Path]:
    source = args.source.lower()

    if source == "ign":
        return ign.download_orbits(
            satellite=args.satellite,
            start=args.begin,
            end=args.end,
            output_dir=args.save_dir,
            center=args.center,
            version=args.version,
            overwrite=args.overwrite,
            uncompress=args.uncompress,
            user=args.ftp_user,
            password=args.ftp_password,
        )

    if source == "cddis":
        if args.uncompress:
            logger.warning(
                "-z is currently implemented for IGN downloads only. "
                "CDDIS files will be downloaded compressed."
            )

        return cddis.download_orbits(
            satellite=args.satellite,
            start=args.begin,
            end=args.end,
            output_dir=args.save_dir,
            center=args.center,
            version=args.version,
            overwrite=args.overwrite,
        )

    raise ValueError(f"Unsupported source: {source}")


def main() -> None:
    args = build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        style="{",
        format="{levelname}: {name} ({funcName}) [{lineno}]: {message}",
    )

    if args.end <= args.begin:
        raise SystemExit("ERROR: --end must be after --begin")

    files = download_sp3_files(args)

    if not files:
        raise SystemExit("ERROR: no SP3 files were downloaded.")

    for file in files:
        print(file)


if __name__ == "__main__":
    main()
