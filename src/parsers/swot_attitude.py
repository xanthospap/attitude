from __future__ import annotations

from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


SWOT_SOLAR_PANEL_PLUS_X = "OBSSD_AM_ZESTSMPOSPX"
SWOT_SOLAR_PANEL_MINUS_X = "OBSSD_AM_ZESTSMPOSMX"


def _parse_utc_z(value: str) -> datetime:
    """
    Parse SWOT timestamps like:
        2024-01-01T12:34:56.789Z
        2024-01-01T12:34:56Z
    """

    value = value.strip()

    if value.endswith("Z"):
        value = value[:-1]

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    raise ValueError(f"Unsupported SWOT timestamp: {value!r}")


def read_swot_qsolp_xml(xml_file: str | Path) -> pd.DataFrame:
    """
    Read a SWOT qsolp XML file.

    Returns a dataframe with columns:
        date_time, left_panel, right_panel

    Angles are returned in radians.
    """

    xml_file = Path(xml_file)

    root = ET.parse(xml_file).getroot()
    data_section = root.find("DATA")

    if data_section is None:
        raise ValueError(f"No DATA section found in {xml_file}")

    data_list = data_section.find("DATA_LIST")

    if data_list is None:
        raise ValueError(f"No DATA_LIST section found in {xml_file}")

    plus_x: dict[datetime, float] = {}
    minus_x: dict[datetime, float] = {}

    for param in data_list.findall("PARAM"):
        mnemo = param.findtext("MNEMO")
        onboard_date = param.findtext("ONBOARD_DATE")
        eng_value = param.findtext("ENG_VALUE")

        if mnemo is None or onboard_date is None or eng_value is None:
            continue

        epoch = _parse_utc_z(onboard_date)

        # CNES/SWOT convention in the existing code:
        # ENG_VALUE / 120 gives degrees. Convert to radians.
        angle = np.radians(float(eng_value) / 120.0)

        if mnemo == SWOT_SOLAR_PANEL_PLUS_X:
            plus_x[epoch] = angle + np.radians(0.2)
        elif mnemo == SWOT_SOLAR_PANEL_MINUS_X:
            minus_x[epoch] = angle + np.radians(-0.2)

    common_epochs = sorted(set(plus_x).intersection(minus_x))

    if not common_epochs:
        raise ValueError(
            f"No simultaneous SWOT solar-panel records found in {xml_file}"
        )

    missing_minus_x = len(set(plus_x) - set(minus_x))
    missing_percent = 100.0 * missing_minus_x / max(len(plus_x), 1)

    if missing_percent > 10.0:
        raise RuntimeError(
            f"Too many non-simultaneous SWOT solar-panel records in {xml_file}: "
            f"{missing_percent:.1f}% missing"
        )

    return pd.DataFrame(
        {
            "date_time": common_epochs,
            "left_panel": [plus_x[t] for t in common_epochs],
            "right_panel": [minus_x[t] for t in common_epochs],
        }
    )
