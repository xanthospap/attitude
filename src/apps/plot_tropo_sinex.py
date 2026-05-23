#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plot parameter solutions from a SINEX_TRO file.

This command-line script is a small plotting front-end for ``tropo_sinex.py``.
It expects ``tropo_sinex.py`` to be importable, either because it is in the
same directory as this script, because it is in the current working directory,
or because its directory is listed in ``PYTHONPATH``.

Examples
--------
Plot ZTD/TROTOT for one station and show the figure interactively::

    python plot_tropo_sinex.py \
        -b 2013:168:00000 \
        -e 2013:169:00000 \
        -s GOPE00CZE \
        -p TROTOT \
        GOP2OPSFIN_20131680000_01D_05M_TRO.TRO

Save the same plot to a PNG file instead of opening an interactive window::

    python plot_tropo_sinex.py \
        -b 2013-06-17T00:00:00 \
        -e 2013-06-18T00:00:00 \
        -s GOPE00CZE \
        -p TROTOT \
        -o gope_ztd.png \
        GOP2OPSFIN_20131680000_01D_05M_TRO.TRO

Date inputs are passed through to ``TropoSinex.get(...)`` and may therefore be
ISO-8601 strings such as ``YYYY-MM-DD`` or ``YYYY-MM-DDTHH:MM:SS``, or SINEX_TRO
epoch strings such as ``YYYY:DOY:SOD``.
"""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from parsers.tropo_sinex import TropoSinex


ScalarValue = Optional[float]
StddevValue = Dict[str, Optional[float]]
SeriesValue = Union[ScalarValue, StddevValue]
TimeSeries = Sequence[Tuple[object, SeriesValue]]


PARAMETER_DESCRIPTIONS = {
    "TROTOT": "Zenith total tropospheric delay",
    "TROWET": "Zenith wet tropospheric delay",
    "TRODRY": "Zenith dry/hydrostatic tropospheric delay",
    "TGNTOT": "North total gradient",
    "TGNWET": "North wet gradient",
    "TGNDRY": "North dry gradient",
    "TGETOT": "East total gradient",
    "TGEWET": "East wet gradient",
    "TGEDRY": "East dry gradient",
    "STDDEV": "Standard deviation of estimated parameters",
    "IWV": "Integrated water vapour",
}


def build_arg_parser() -> argparse.ArgumentParser:
    """Create and return the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description="Plot a station parameter time series from a SINEX_TRO file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "tropo_sinex_file",
        metavar="TROPO_SINEX_FILE",
        help="Path to the SINEX_TRO file to read. Plain text and .gz files are supported by tropo_sinex.py.",
    )
    parser.add_argument(
        "-b",
        "--begin",
        required=False,
        default="1980-01-01",
        help="Inclusive start date/time. Examples: 2013:168:00000, 2013-06-17, 2013-06-17T00:00:00.",
    )
    parser.add_argument(
        "-e",
        "--end",
        required=False,
        default=datetime.datetime.now().strftime("%Y-%m-%d"),
        help="Exclusive end date/time. Examples: 2013:169:00000, 2013-06-18, 2013-06-18T00:00:00.",
    )
    parser.add_argument(
        "-s",
        "--station",
        required=True,
        help="Station site code, normally the 9-character Site Code, e.g. GOPE00CZE.",
    )
    parser.add_argument(
        "-p",
        "--parameter",
        required=True,
        choices=sorted(PARAMETER_DESCRIPTIONS),
        type=str.upper,
        help="Tropospheric parameter type to plot.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output image filename. If omitted, the plot is shown interactively.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="Output image DPI when --output is used.",
    )
    parser.add_argument(
        "--marker",
        default=".",
        help="Matplotlib marker style for plotted samples. Use an empty string for no marker.",
    )
    parser.add_argument(
        "--line-style",
        default="-",
        help="Matplotlib line style. Use an empty string to plot markers only.",
    )
    parser.add_argument(
        "--list-available",
        action="store_true",
        help="Print available sites and parameters from the file before plotting.",
    )
    return parser


def remove_missing_samples(
    epochs: Sequence[object], values: Sequence[Optional[float]]
) -> Tuple[List[object], List[float]]:
    """Return epochs and values after dropping missing ``None`` samples."""

    clean_epochs: List[object] = []
    clean_values: List[float] = []
    for epoch, value in zip(epochs, values):
        if value is not None:
            clean_epochs.append(epoch)
            clean_values.append(value)
    return clean_epochs, clean_values


def plot_scalar_series(
    ax: plt.Axes,
    series: TimeSeries,
    label: str,
    marker: str,
    line_style: str,
) -> int:
    """Plot an ordinary scalar parameter and return the number of plotted samples."""

    epochs = [epoch for epoch, _ in series]
    values = [value for _, value in series]
    clean_epochs, clean_values = remove_missing_samples(epochs, values)  # type: ignore[arg-type]
    if clean_values:
        ax.plot(clean_epochs, clean_values, linestyle=line_style, marker=marker, label=label)
    return len(clean_values)


def plot_stddev_series(
    ax: plt.Axes,
    series: TimeSeries,
    marker: str,
    line_style: str,
) -> int:
    """Plot the special ``STDDEV`` result returned by ``TropoSinex.get``.

    ``STDDEV`` is special because SINEX_TRO may include several STDDEV columns,
    each one associated with the parameter immediately before it.  The
    ``TropoSinex`` class returns each epoch as a dictionary such as::

        {"TROTOT": 0.0005, "TGNTOT": 0.0001, "TGETOT": 0.0001}

    This function plots one line per dictionary key.
    """

    owners: List[str] = sorted(
        {
            owner
            for _, value in series
            if isinstance(value, dict)
            for owner in value.keys()
        }
    )

    plotted = 0
    for owner in owners:
        epochs: List[object] = []
        values: List[Optional[float]] = []
        for epoch, value in series:
            if isinstance(value, dict):
                epochs.append(epoch)
                values.append(value.get(owner))
        clean_epochs, clean_values = remove_missing_samples(epochs, values)
        if clean_values:
            ax.plot(clean_epochs, clean_values, linestyle=line_style, marker=marker, label=f"STDDEV({owner})")
            plotted += len(clean_values)
    return plotted


def format_time_axis(ax: plt.Axes) -> None:
    """Apply a readable date/time formatter to the x-axis."""

    locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    ax.figure.autofmt_xdate()


def make_plot(
    sinex: TropoSinex,
    station: str,
    parameter: str,
    begin: str,
    end: str,
    output: Optional[str],
    dpi: int,
    marker: str,
    line_style: str,
) -> None:
    """Fetch a time series using ``TropoSinex.get`` and plot it."""

    series = sinex.get(station, parameter, begin, end)
    if not series:
        raise SystemExit(
            f"No samples found for station={station!r}, parameter={parameter!r}, interval=[{begin}, {end})."
        )

    fig, ax = plt.subplots(figsize=(10, 5))

    if parameter == "STDDEV":
        plotted_count = plot_stddev_series(ax, series, marker=marker, line_style=line_style)
        ylabel = "STDDEV"
    else:
        plotted_count = plot_scalar_series(
            ax,
            series,
            label=parameter,
            marker=marker,
            line_style=line_style,
        )
        ylabel = parameter

    if plotted_count == 0:
        raise SystemExit(
            f"All {len(series)} samples are missing for station={station!r}, parameter={parameter!r}, interval=[{begin}, {end})."
        )

    parameter_label = PARAMETER_DESCRIPTIONS.get(parameter, parameter)
    ax.set_title(f"{station.upper()} {parameter}: {parameter_label}")
    ax.set_xlabel("Epoch")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    format_time_axis(ax)

    if parameter == "STDDEV":
        ax.legend(loc="best")
    elif len(ax.lines) > 1:
        ax.legend(loc="best")

    fig.tight_layout()

    if output:
        output_path = Path(output)
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
        print(f"Saved plot to {output_path}")
    else:
        plt.show()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Program entry point."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    sinex = TropoSinex(args.tropo_sinex_file)

    if args.list_available:
        print("Available parameters:", ", ".join(sinex.available_parameters()))
        print("Available sites:", ", ".join(sinex.available_sites()))

    make_plot(
        sinex=sinex,
        station=args.station,
        parameter=args.parameter,
        begin=args.begin,
        end=args.end,
        output=args.output,
        dpi=args.dpi,
        marker=args.marker,
        line_style=args.line_style,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
