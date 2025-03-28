# -*- coding: utf-8 -*-

"""preprocess.py

[Uncompress,] read, interpolate and concatenate quaternion files.
"""

# import glob
import logging
import pathlib
import tarfile
from os import remove
from os.path import join, dirname, exists

import numpy as np
import pandas as pd
import astropy.time as atime
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp

from prepattitude.configuration import SATELLITE_INFO, GAP_THRESHOLD


# LOGGING_LEVEL = logging.INFO
LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)
logger = logging.getLogger(__name__)


def _uncompress_files(qfns: list[str]) -> list[str]:
    """Safely uncompress files in its directory."""
    ufiles = []
    for cfile in qfns:
        with tarfile.open(cfile, "r") as tgz:
            members = tgz.getmembers()
            for member in members:
                if member.name.endswith(".DBL"):
                    try:
                        tgz.extract(member, filter="data")
                        ufiles.append(join(dirname(cfile), member.name))
                        logger.debug(f"Extracting file {member.name}.")
                    except tarfile.FilterError:
                        logger.error(
                            f"Error extracting file {member.name}. Check archive {cfile}."
                        )
                        raise
    return ufiles


def _read_single_file(satellite: str, qfile: pathlib.Path) -> pd.DataFrame:
    """Read a single quaternion file to a pandas DataFrame."""
    # default arguments
    kwargs = {
        # 'delim_whitespace': True,
        "sep": "\s+",
        "comment": "#",
        "header": None,
    }

    logger.info(f"Reading quaternion file {qfile}.")
    # set useful columns
    match satellite:
        case "ja1" | "ja2" | "ja3":
            try:
                sv_args = {
                    "usecols": [0, 1, 3, 6, 9, 12],
                    "names": ["_date", "_time"] + [f"q{i}" for i in range(4)],
                }
                df = pd.read_csv(qfile, **kwargs, **sv_args)
            except pd.errors.ParserError:  # it's a 'qsolp' file
                sv_args = {
                    "usecols": [0, 1, 3, 6],
                    "names": ["_date", "_time", "left_panel", "right_panel"],
                }
                df = pd.read_csv(qfile, **kwargs, **sv_args)
        case "s3a" | "s3b" | "s6a":
            sv_args = {
                "usecols": [0, 1, 2, 3, 4, 5],
                "names": ["_date", "_time"] + [f"q{i}" for i in range(4)],
            }
            df = pd.read_csv(qfile, **kwargs, **sv_args)

    # parse date & time
    date_col = df.iloc[:, 0]
    time_col = df.iloc[:, 1]
    df["date_time"] = pd.to_datetime(
        date_col + " " + time_col, format="%Y/%m/%d %H:%M:%S.%f"
    )
    # df.set_index('date_time', inplace=True)

    return df.drop(columns=["_date", "_time"])


def _fix_time(satellite: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Change the time scale and format of the DataFrame.
    Input is np.datetime64 in UTC (Jason) or GPST (Sentinel).
    Output is MJD (float) in TT.
    """
    logger.info("Fixing time scale.")
    # change time scale to TT
    match satellite:
        case "ja1" | "ja2" | "ja3":
            # Jason quaternions are given at UTC times
            tt = atime.Time(df["date_time"].to_numpy(), scale="utc").tt
        case "s3a" | "s3b" | "s6a":
            # Sentinel quaternions are given at GPST times
            tt = atime.Time(
                (df["date_time"] + np.timedelta64(19, "s")).to_numpy(), scale="tai"
            ).tt
    df["date_time"] = tt.to_value(format="datetime64")
    logger.debug(df)
    # set date_time as index (replaced)
    return df.set_index("date_time")


def _time2mjd(time_array, scale="tt"):
    t = atime.Time(time_array, format="datetime64", scale=scale)
    mjd_days = t.mjd.astype(int)
    sec_of_day = (t.mjd - mjd_days) * 86400
    return mjd_days, sec_of_day


def _interpolate(satellite: str, df: pd.DataFrame, Nsec: float) -> pd.DataFrame:
    """
    Compute scipy.spatial.transform.Rotation objects from quaternions and
    interpolate at N sec interval using scipy.spatial.transform.Slerp.

    For Jason satellites, also interpolate (linearly) solar panel angles.
    """
    # make sure dataframe is ordered chronologically, and everry duplicate
    # (if any) is replaced by the (multi-occurancies) mean value(s)
    df = df.sort_index().groupby(df.index).mean()

    # compute rotations
    rotations = df.loc[:, ["q0", "q1", "q2", "q3"]].to_numpy()
    rotations = R.concatenate([R.from_quat(q, scalar_first=True) for q in rotations])
    logger.debug(rotations)

    # create Slerp object
    times_ = atime.Time(df.index.values, scale="tt").mjd
    slerp = Slerp(times_, rotations)

    # construct time array at constant intervals of N sec
    times = np.arange(start=times_[0], stop=times_[-1], step=Nsec / 86400.0)

    # interpolate
    logger.info("Interpolating quaternions.")
    rotations = slerp(times)

    # Jason satellite; interpolate solar panel angles
    if satellite.startswith("ja"):
        logger.info("Interpolating solar panel angles.")

        # TODO: FIX THIS HACK!
        # Make it work with np.datetime64 indices!
        df.index = times_

        df_ = (
            df[["left_panel", "right_panel"]]
            .reindex(df.index.union(times))
            .interpolate(method="polynomial", order=1)
        )
        df_ = df_[~df_.index.isin(df.index.difference(times))]
        df_.index = atime.Time(df_.index.to_numpy(), format="mjd", scale="tt").to_value(
            format="datetime64"
        )
        logger.debug(df_.shape, df_.columns, df_.index)

    # construct the new DataFrame
    df = pd.DataFrame(
        data=rotations.as_quat(scalar_first=True),
        index=times,
        columns=[f"q{i}" for i in range(4)],
    )
    logger.debug(df.shape, df.columns, df.index)

    # fix index
    df.index = atime.Time(df.index.to_numpy(), format="mjd", scale="tt").to_value(
        format="datetime64"
    )

    # Jason satellite; merge
    if satellite.startswith("ja"):
        df = pd.merge(df, df_, left_index=True, right_index=True)

    return df


def _process_single_file(
    satellite: str, qfile: pathlib.Path, solp_file: pathlib.Path = None
) -> pd.DataFrame:
    """Process a single quaternion file, or a pair (body -- panels) in case of Jason satellite."""
    # read "body" q-file
    df = _read_single_file(satellite, qfile)

    # Jason satellite; read and merge "panels" file
    if solp_file is not None:
        df_ = _read_single_file(satellite, solp_file)
        df = pd.merge(df, df_, how="left", on="date_time").sort_values("date_time")

    # fix time scale and return data frame
    return _fix_time(satellite, df)


def _process_batch(satellite: str, Nsec, df):
    # interpolate at regular intervals
    df = _interpolate(satellite, df, Nsec)

    # convert time format
    mjd_days, sec_of_day = _time2mjd(df.index.values, scale="tt")
    df["MJDay"] = mjd_days
    df["SecOfDay"] = sec_of_day

    return df.reset_index(drop=True).set_index(["MJDay", "SecOfDay"])


def _process_jason_files(satellite: str, Nsec: float, qfns: list[str]) -> pd.DataFrame:
    """Walk through the given file list, read, process and concatenate quaternion files."""
    DATA_TYPES = SATELLITE_INFO[satellite]["data_types"]

    # make the file pairs (body+solar panels)
    fileps = [
        (file, file.replace("body", "solp"))
        for file in [str(f) for f in qfns]
        if "body" in file
    ]

    # process each single file pair
    dfs = []
    for q in fileps:
        dfs.append(_process_single_file(satellite, *q))

    # interpolate merged dataframes
    df = _process_batch(satellite, Nsec, pd.concat(dfs))

    # remove raw files
    [remove(f) for f in qfns if exists(f)]

    # return a single pandas DataFrame
    return df


def _process_sentinel_files(
    satellite: str, Nsec: float, qfns: list[str]
) -> pd.DataFrame:
    """Walk through the given file list, read, process and concatenate quaternion files."""
    # extract the DBL files
    qfns = _uncompress_files(qfns)

    # process each file
    dfs = []
    for qfile in qfns:
        dfs.append(_process_single_file(satellite, qfile))

    # interpolate merged dataframes
    df = _process_batch(satellite, Nsec, pd.concat(dfs))

    # delete DBL files
    [remove(f) for f in qfns if exists(f)]

    # return a single pandas DataFrame
    return df


# def _serialize(satellite: str, save_dir: str, df: pd.DataFrame) -> None:
#    """Serialize the concatenated quaternion data to pickle."""
#    df.to_pickle(pathlib.Path(save_dir, f"qua_{satellite}.pkl"))


# def _deserialize(satellite: str, save_dir: str) -> pd.DataFrame:
#    """Read a pandas DataFrame from a pickle file."""
#    return pd.read_pickle(pathlib.Path(save_dir, f"qua_{satellite}.pkl"))


def preprocess(satellite: str, Nsec: float, qfns: list[str]) -> None:
    """Process quaternion files and create CSV files."""
    logger.info(f"Processing {satellite} quaternion files.")
    if qfns == []:
        logger.error(
            f"Got empty list of downloaded files (sat. {satellite}). Nothing to do."
        )
        return
    match satellite:
        case "ja1" | "ja2" | "ja3":
            df = _process_jason_files(satellite, Nsec, qfns)
        case "s3a" | "s3b" | "s6a":
            df = _process_sentinel_files(satellite, Nsec, qfns)

    # output
    save_dir = dirname(qfns[0])
    csv_file = f"{save_dir}/qua_{satellite}.csv"
    logger.info(f"Quaternions file is saved to {csv_file}.")
    df.to_csv(csv_file, sep=" ", float_format="%.12e", header=False)
