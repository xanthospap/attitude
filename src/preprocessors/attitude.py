from __future__ import annotations

import logging
import tarfile
from pathlib import Path

import astropy.time as atime
import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp

from parsers.swot_attitude import read_swot_qsolp_xml


logger = logging.getLogger(__name__)


JASON_SATELLITES = {"ja1", "ja2", "ja3"}
SENTINEL_SATELLITES = {"s3a", "s3b", "s6a"}
SWOT_SATELLITES = {"swo"}

SUPPORTED_SATELLITES = JASON_SATELLITES | SENTINEL_SATELLITES | SWOT_SATELLITES

QUATERNION_COLUMNS = ["q0", "q1", "q2", "q3"]
SOLAR_PANEL_COLUMNS = ["left_panel", "right_panel"]


def _name(path: str | Path) -> str:
    return Path(path).name.lower()


def _is_qbody(path: str | Path) -> bool:
    return "qbody" in _name(path) or "body" in _name(path)


def _is_qsolp(path: str | Path) -> bool:
    return "qsolp" in _name(path) or "solp" in _name(path)


def _read_text_attitude_file(
    qfile: str | Path,
    usecols: list[int],
    names: list[str],
) -> pd.DataFrame:
    qfile = Path(qfile)

    df = pd.read_csv(
        qfile,
        sep=r"\s+",
        comment="#",
        header=None,
        usecols=usecols,
        names=names,
    )

    df["date_time"] = pd.to_datetime(
        df["_date"].astype(str) + " " + df["_time"].astype(str),
        format="%Y/%m/%d %H:%M:%S.%f",
    )

    return df.drop(columns=["_date", "_time"])


def read_attitude_file(satellite: str, qfile: str | Path) -> pd.DataFrame:
    """
    Read one local attitude file.

    Output columns are either:
        date_time, q0, q1, q2, q3

    or:
        date_time, left_panel, right_panel
    """

    satellite = satellite.lower()
    qfile = Path(qfile)
    name = qfile.name.lower()

    logger.info("Reading attitude file %s", qfile)

    if satellite not in SUPPORTED_SATELLITES:
        raise ValueError(f"Unsupported satellite: {satellite}")

    if satellite == "swo" and _is_qsolp(name):
        return read_swot_qsolp_xml(qfile)

    if satellite == "ja1":
        if _is_qbody(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 2, 3, 4, 5],
                names=["_date", "_time", *QUATERNION_COLUMNS],
            )

        if _is_qsolp(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 2, 3],
                names=["_date", "_time", *SOLAR_PANEL_COLUMNS],
            )

        raise ValueError(f"Cannot identify Jason-1 attitude file type: {qfile}")

    if satellite in {"ja2", "ja3", "swo"}:
        if _is_qbody(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 3, 6, 9, 12],
                names=["_date", "_time", *QUATERNION_COLUMNS],
            )

        if _is_qsolp(name):
            return _read_text_attitude_file(
                qfile,
                usecols=[0, 1, 3, 6],
                names=["_date", "_time", *SOLAR_PANEL_COLUMNS],
            )

        raise ValueError(f"Cannot identify attitude file type: {qfile}")

    if satellite in SENTINEL_SATELLITES:
        return _read_text_attitude_file(
            qfile,
            usecols=[0, 1, 2, 3, 4, 5],
            names=["_date", "_time", *QUATERNION_COLUMNS],
        )

    raise ValueError(f"Unsupported satellite: {satellite}")


def _fix_time(satellite: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert input times to TT datetime64 and set them as the dataframe index.

    Jason and SWOT files are treated as UTC.
    Sentinel files are treated as GPST, represented as TAI after adding 19 seconds.
    """

    satellite = satellite.lower()

    if satellite in JASON_SATELLITES | SWOT_SATELLITES:
        tt = atime.Time(df["date_time"].to_numpy(), scale="utc").tt

    elif satellite in SENTINEL_SATELLITES:
        tai_datetimes = df["date_time"] + np.timedelta64(19, "s")
        tt = atime.Time(tai_datetimes.to_numpy(), scale="tai").tt

    else:
        raise ValueError(f"Unsupported satellite: {satellite}")

    df = df.copy()
    df["date_time"] = tt.to_value(format="datetime64")

    return df.set_index("date_time")


def _time_to_mjd_and_sod(
    time_array, scale: str = "tt"
) -> tuple[np.ndarray, np.ndarray]:
    t = atime.Time(time_array, format="datetime64", scale=scale)
    mjd_days = t.mjd.astype(int)
    sec_of_day = (t.mjd - mjd_days) * 86400.0

    return mjd_days, sec_of_day


def _interpolate(
    df: pd.DataFrame,
    nsec: float,
    times: np.ndarray | None = None,
) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Interpolate either body quaternions or solar-panel angles.

    Quaternion interpolation uses SLERP.
    Solar-panel interpolation is linear in time.
    """

    if df.empty:
        raise ValueError("Cannot interpolate an empty dataframe")

    df = df.sort_index().groupby(df.index).mean()

    source_times = atime.Time(df.index.values, scale="tt").mjd

    if times is None:
        times = np.arange(
            start=source_times[0],
            stop=source_times[-1],
            step=nsec / 86400.0,
        )

    if all(col in df.columns for col in QUATERNION_COLUMNS):
        logger.info("Interpolating body quaternions")

        quaternions = df[QUATERNION_COLUMNS].to_numpy()

        rotations = R.from_quat(quaternions, scalar_first=True)
        slerp = Slerp(source_times, rotations)
        interpolated = slerp(times)

        out = pd.DataFrame(
            data=interpolated.as_quat(scalar_first=True),
            index=times,
            columns=QUATERNION_COLUMNS,
        )

    elif all(col in df.columns for col in SOLAR_PANEL_COLUMNS):
        logger.info("Interpolating solar-panel angles")

        numeric = pd.DataFrame(
            data=df[SOLAR_PANEL_COLUMNS].to_numpy(),
            index=source_times,
            columns=SOLAR_PANEL_COLUMNS,
        )

        target_index = pd.Index(times, name="mjd")

        out = (
            numeric.reindex(numeric.index.union(target_index))
            .sort_index()
            .interpolate(method="index")
            .loc[target_index]
        )

    else:
        raise ValueError(
            "Input dataframe has neither quaternion columns nor solar-panel columns"
        )

    out.index = atime.Time(
        out.index.to_numpy(),
        format="mjd",
        scale="tt",
    ).to_value(format="datetime64")

    return out, times


def _to_output_index(df: pd.DataFrame) -> pd.DataFrame:
    mjd_days, sec_of_day = _time_to_mjd_and_sod(df.index.values, scale="tt")

    df = df.copy()
    df["MJDay"] = mjd_days
    df["SecOfDay"] = sec_of_day

    return df.reset_index(drop=True).set_index(["MJDay", "SecOfDay"])


def _extract_sentinel_dbl_files(files: list[Path]) -> list[Path]:
    """
    Extract Sentinel DBL files from tar archives.

    If an input file is already a .DBL file, keep it.
    """

    extracted: list[Path] = []

    for file in files:
        file = Path(file)

        if file.name.upper().endswith(".DBL"):
            extracted.append(file)
            continue

        target_dir = file.parent

        with tarfile.open(file, "r:*") as archive:
            for member in archive.getmembers():
                if not member.name.upper().endswith(".DBL"):
                    continue

                archive.extract(member, path=target_dir, filter="data")

                extracted_file = target_dir / member.name
                extracted.append(extracted_file)

                logger.debug("Extracted %s from %s", member.name, file)

    return extracted


def _matching_qsolp_file(qbody_file: Path, files_by_name: dict[str, Path]) -> Path:
    expected_name = qbody_file.name.lower().replace("qbody", "qsolp")

    if expected_name in files_by_name:
        return files_by_name[expected_name]

    expected_file = qbody_file.with_name(qbody_file.name.replace("qbody", "qsolp"))

    if expected_file.exists():
        return expected_file

    raise FileNotFoundError(
        f"Could not find solar-panel file matching body file {qbody_file}. "
        f"Expected {expected_name}"
    )


def _process_body_and_panel_files(
    satellite: str,
    body_files: list[Path],
    panel_files: list[Path],
    nsec: float,
) -> pd.DataFrame:
    if not body_files:
        raise ValueError(f"No qbody files found for {satellite}")

    if not panel_files:
        raise ValueError(f"No qsolp files found for {satellite}")

    body_dfs = [
        _fix_time(satellite, read_attitude_file(satellite, file)) for file in body_files
    ]

    panel_dfs = [
        _fix_time(satellite, read_attitude_file(satellite, file))
        for file in panel_files
    ]

    df_body, times = _interpolate(pd.concat(body_dfs), nsec)
    df_panel, _ = _interpolate(pd.concat(panel_dfs), nsec, times=times)

    return _to_output_index(
        pd.merge(df_body, df_panel, left_index=True, right_index=True)
    )


def _process_jason_files(
    satellite: str,
    nsec: float,
    qfns: list[str | Path],
) -> pd.DataFrame:
    files = [Path(file) for file in qfns]
    files_by_name = {file.name.lower(): file for file in files}

    body_files = sorted(file for file in files if _is_qbody(file))
    panel_files = [_matching_qsolp_file(file, files_by_name) for file in body_files]

    return _process_body_and_panel_files(
        satellite=satellite,
        body_files=body_files,
        panel_files=panel_files,
        nsec=nsec,
    )


def _process_swot_files(
    satellite: str,
    nsec: float,
    qfns: list[str | Path],
) -> pd.DataFrame:
    files = [Path(file) for file in qfns]

    body_files = sorted(file for file in files if _is_qbody(file))
    panel_files = sorted(file for file in files if _is_qsolp(file))

    return _process_body_and_panel_files(
        satellite=satellite,
        body_files=body_files,
        panel_files=panel_files,
        nsec=nsec,
    )


def _process_sentinel_files(
    satellite: str,
    nsec: float,
    qfns: list[str | Path],
    cleanup_extracted: bool = True,
) -> pd.DataFrame:
    files = [Path(file) for file in qfns]
    attitude_files = _extract_sentinel_dbl_files(files)

    if not attitude_files:
        raise ValueError(f"No Sentinel DBL files found for {satellite}")

    dfs = [
        _fix_time(satellite, read_attitude_file(satellite, file))
        for file in attitude_files
    ]

    df, _ = _interpolate(pd.concat(dfs), nsec)
    df = _to_output_index(df)

    if cleanup_extracted:
        original_files = {file.resolve() for file in files}

        for file in attitude_files:
            try:
                if file.resolve() not in original_files:
                    file.unlink()
            except FileNotFoundError:
                pass

    return df


def _clip_output_range(
    df: pd.DataFrame,
    start=None,
    end=None,
) -> pd.DataFrame:
    """
    Clip output dataframe indexed by (MJDay, SecOfDay) to [start, end).

    start/end are naive datetimes interpreted in TT-output comparison space.
    For this CLI use case, that is acceptable because the preprocessor already
    converted all file times to TT before output.
    """

    if start is None and end is None:
        return df

    index_times = atime.Time(
        df.index.get_level_values("MJDay").to_numpy()
        + df.index.get_level_values("SecOfDay").to_numpy() / 86400.0,
        format="mjd",
        scale="tt",
    ).to_datetime()

    mask = np.ones(len(df), dtype=bool)

    if start is not None:
        mask &= index_times >= start

    if end is not None:
        mask &= index_times < end

    return df.loc[mask]


def preprocess_attitude(
    satellite: str,
    qfns: list[str | Path],
    nsec: float = 5.0,
    start=None,
    end=None,
    output_file: str | Path | None = None,
) -> Path:
    """
    Process local attitude files and write the interpolated output CSV.

    This function does not download anything.
    """

    satellite = satellite.lower()
    files = [Path(file) for file in qfns]

    if not files:
        raise ValueError(f"No attitude files provided for satellite {satellite}")

    if satellite in JASON_SATELLITES:
        df = _process_jason_files(satellite, nsec, files)

    elif satellite in SENTINEL_SATELLITES:
        df = _process_sentinel_files(satellite, nsec, files)

    elif satellite in SWOT_SATELLITES:
        df = _process_swot_files(satellite, nsec, files)

    else:
        raise ValueError(f"Unsupported satellite: {satellite}")

    if start is not None or end is not None:
        df = _clip_output_range(df, start=start, end=end)

    if output_file is None:
        output_file = files[0].parent / f"qua_{satellite}.csv"
    else:
        output_file = Path(output_file)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Writing preprocessed attitude file to %s", output_file)

    df.dropna().to_csv(
        output_file,
        sep=" ",
        float_format="%.12e",
        header=False,
    )

    return output_file


# Backwards-compatible alias while refactoring callers.
preprocess = preprocess_attitude
