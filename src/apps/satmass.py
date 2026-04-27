from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from sources.ids import download_satmass
from parsers.cnes_mass import parse_cnes_mass


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def plot_mass(data: dict) -> None:
    import matplotlib.pyplot as plt

    epochs = [row[0] for row in data["data"]]
    delta_mass = [row[1] for row in data["data"]]
    delta_cog = [row[2] for row in data["data"]]

    fig, ax = plt.subplots(2, 1, sharex=True)

    ax[0].scatter(epochs, delta_mass, zorder=3)
    ax[0].plot(epochs, delta_mass, zorder=1)
    ax[0].set_ylabel("Mass variations [kg]")
    ax[0].grid(True)

    for index, label in enumerate(("dX", "dY", "dZ")):
        values = [row[index] for row in delta_cog]
        ax[1].scatter(epochs, values, zorder=3, label=label)
        ax[1].plot(epochs, values, zorder=1, label="_nolegend_")

    ax[1].set_ylabel("CoG variations [m]")
    ax[1].set_xlabel("Time")
    ax[1].legend()
    ax[1].grid(True)

    if "sat" in data:
        fig.suptitle(f"Satellite {data['sat']}")

    plt.show()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="satmass",
        description="Download, parse, and optionally plot IDS/CNES satellite mass files.",
    )

    source = parser.add_mutually_exclusive_group(required=True)

    source.add_argument(
        "-s",
        "--satellite",
        help="Satellite ID, e.g. ja3, s3a, s3b.",
    )

    source.add_argument(
        "-m",
        "--mass-file",
        type=Path,
        help="Existing local CNES mass file.",
    )

    parser.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory where downloaded files are saved.",
    )

    parser.add_argument(
        "-b",
        "--begin-date",
        type=parse_date,
        default=datetime.min,
        metavar="YYYY-MM-DD",
        help="Only include records on or after this date.",
    )

    parser.add_argument(
        "-e",
        "--end-date",
        type=parse_date,
        default=datetime.max,
        metavar="YYYY-MM-DD",
        help="Only include records before this date.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload the file even if it already exists.",
    )

    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download the file and stop.",
    )

    parser.add_argument(
        "--plot",
        action="store_true",
        help="Plot mass and center-of-gravity variations.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.satellite:
        mass_file = download_satmass(
            satellite=args.satellite,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
        )
    else:
        mass_file = args.mass_file

    print(mass_file)

    if args.download_only:
        return

    data = parse_cnes_mass(
        mass_file,
        start=args.begin_date,
        stop=args.end_date,
    )

    print(f"sat: {data.get('sat', 'unknown')}")
    print(f"mass_init: {data.get('mass_init', 'unknown')}")
    print(f"cog_init: {data.get('cog_init', 'unknown')}")
    print(f"records: {len(data['data'])}")

    if args.plot:
        plot_mass(data)


if __name__ == "__main__":
    main()
