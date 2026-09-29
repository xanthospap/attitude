from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

from products.config import KNOWN_SATELLITES, PreparationContext, parse_utc_datetime
from products.prepare import (
    prepare_aod1b,
    prepare_atmospheric_tides,
    prepare_dpod,
    prepare_eop,
    prepare_satellite_files,
    prepare_space_weather,
)


RL06_TIDES = ("k1", "l2", "m2", "n2", "p1", "r2", "r3", "s1", "s2", "s3", "t2", "t3")


def _utc(value: str) -> dt.datetime:
    try:
        return parse_utc_datetime(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        style="{",
        format="{levelname}: {name}: {message}",
    )


def _context(
    config: dict,
    root: Path,
    start: dt.datetime,
    stop: dt.datetime,
    *,
    overwrite: bool,
    decompress: bool,
    satellites: list[dict] | None = None,
) -> PreparationContext:
    if stop <= start:
        raise ValueError("--end must be after --begin")
    return PreparationContext(
        config=config,
        root=root.expanduser().resolve(),
        start=start,
        stop=stop,
        satellites=satellites or [],
        overwrite=overwrite,
        decompress=decompress,
    )


def _common(parser: argparse.ArgumentParser, *, interval: bool = True) -> None:
    if interval:
        parser.add_argument("-b", "--begin", required=True, type=_utc)
        parser.add_argument("-e", "--end", required=True, type=_utc)
    parser.add_argument("--root-dir", type=Path, default=Path.cwd())
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--decompress", action="store_true", default=True)
    parser.add_argument("--no-decompress", dest="decompress", action="store_false")
    parser.add_argument("-v", "--verbose", action="store_true")


def _report(result) -> int:
    for path in result.available:
        print(path)
    for warning in result.warnings:
        logging.getLogger(__name__).warning("%s", warning)
    return 0


def main_dpod() -> int:
    parser = argparse.ArgumentParser(
        prog="dpoddwn",
        description="Download a DPOD SINEX/frequency-correction pair.",
    )
    parser.add_argument("--sinex", required=True)
    parser.add_argument("--frequency-corrections", required=True)
    _common(parser, interval=False)
    args = parser.parse_args()
    _logging(args.verbose)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    config = {
        "a-priori-coordinates": {
            "sinex": args.sinex,
            "dpod_frequency_cor": args.frequency_corrections,
        }
    }
    context = _context(
        config,
        args.root_dir,
        now,
        now + dt.timedelta(seconds=1),
        overwrite=args.overwrite,
        decompress=args.decompress,
    )
    return _report(prepare_dpod(context))


def main_eop() -> int:
    parser = argparse.ArgumentParser(
        prog="eopdwn",
        description="Download an IERS C04 EOP file covering a UTC interval.",
    )
    parser.add_argument("-o", "--output", required=True)
    _common(parser)
    args = parser.parse_args()
    _logging(args.verbose)
    config = {"eop": args.output}
    context = _context(
        config,
        args.root_dir,
        args.begin,
        args.end,
        overwrite=args.overwrite,
        decompress=args.decompress,
    )
    return _report(prepare_eop(context))


def main_space_weather() -> int:
    parser = argparse.ArgumentParser(
        prog="swdwn",
        description="Download CelesTrak space-weather data covering a UTC interval.",
    )
    parser.add_argument("-o", "--output", required=True)
    _common(parser)
    args = parser.parse_args()
    _logging(args.verbose)
    config = {"space-weather-data": {"celestrak_csv": args.output}}
    context = _context(
        config,
        args.root_dir,
        args.begin,
        args.end,
        overwrite=args.overwrite,
        decompress=args.decompress,
    )
    return _report(prepare_space_weather(context))


def main_satman() -> int:
    parser = argparse.ArgumentParser(
        prog="satmandwn",
        description="Download an IDS/CNES satellite maneuver history.",
    )
    parser.add_argument("-s", "--satellite", required=True)
    parser.add_argument("-o", "--output", required=True)
    _common(parser, interval=False)
    args = parser.parse_args()
    _logging(args.verbose)
    if args.satellite.lower() not in KNOWN_SATELLITES:
        parser.error(f"unknown satellite identifier {args.satellite!r}")
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    entry = {"satellite": args.satellite.lower(), "cnes_maneuver": args.output}
    context = _context(
        {},
        args.root_dir,
        now,
        now + dt.timedelta(seconds=1),
        overwrite=args.overwrite,
        decompress=args.decompress,
        satellites=[entry],
    )
    return _report(prepare_satellite_files(context))


def main_aod1b() -> int:
    parser = argparse.ArgumentParser(
        prog="aod1bdwn",
        description="Download AOD1B dealiasing or RL06 atmospheric-tide files.",
    )
    parser.add_argument("--kind", required=True, choices=["dealiasing", "atmospheric-tides"])
    parser.add_argument("--release", required=True, choices=["RL06", "RL07"])
    parser.add_argument("-d", "--output-dir", required=True)
    _common(parser)
    args = parser.parse_args()
    _logging(args.verbose)

    if args.kind == "dealiasing":
        config = {
            "dealiasing": {
                "model": f"AOD1B {args.release}",
                "data-dir": args.output_dir,
            }
        }
        context = _context(
            config,
            args.root_dir,
            args.begin,
            args.end,
            overwrite=args.overwrite,
            decompress=args.decompress,
        )
        return _report(prepare_aod1b(context))

    files = {name: f"AOD1B_ATM_{name.upper()}_06.asc" for name in RL06_TIDES}
    config = {
        "atmospheric-tide": {
            "model": f"AOD1B {args.release}",
            "data_dir": args.output_dir,
            "tide_atlas_from_aod1b": files,
        }
    }
    context = _context(
        config,
        args.root_dir,
        args.begin,
        args.end,
        overwrite=args.overwrite,
        decompress=args.decompress,
    )
    return _report(prepare_atmospheric_tides(context))
