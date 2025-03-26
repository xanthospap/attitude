# -*- coding: utf-8 -*-

"""Configuration module."""


# NOTE:
# Change the next constant choose your working satellite.
# Valid choices are the keys of the dictionary `_SATELLITE_INFO`.
# SATELLITE = "ja3"
# SATELLITE = "s3a"
# SATELLITE = "s3b"
# SATELLITE = "s6a"

# NOTE:
# Enter a valid path for storing the quaternion files.
# SAVE_DIR = f"./q/{SATELLITE}"  # base directory for quaternion files

# NOTE:
# Maximum allowed gap in seconds (for Sentinel satellites mostly).
# Interpolate if exceeded.
GAP_THRESHOLD = 10

# ***

SATELLITE_INFO = {
    "ja3": {
        "name": "Jason-3",
        "launch_year": 2016,
        "base_url": "https://cddis.nasa.gov/archive/doris/ancillary/quaternions",
        "data_types": ["qbody", "qsolp"]
    },
    "s3a": {
        "name": "Sentinel-3A",
        "launch_year": 2016,
        "base_url": "Sentinel-3/AUX/AUX_PROQUA",
        "data_types": None
    },
    "s3b": {
        "name": "Sentinel-3B",
        "launch_year": 2018,
        "base_url": "Sentinel-3/AUX/AUX_PROQUA",
        "data_types": None
    },
    "s6a": {
        "name": "Sentinel-6A",
        "launch_year": 2020,
        "base_url": "Sentinel-6/AUX/AUX_PROQUA",
        "data_types": None
    }
}

# SAT_NAME = SATELLITE_INFO[SATELLITE]["name"]
def CUTOFF_YEAR(satellite):
    return SATELLITE_INFO[SATELLITE]["launch_year"]
# BASE_URL = SATELLITE_INFO[SATELLITE]["base_url"]
# DATA_TYPES = SATELLITE_INFO[SATELLITE]["data_types"]


#__all__ = (
#    "SATELLITE",
#    "SAT_NAME", "CUTOFF_YEAR", "BASE_URL", "DATA_TYPES",
#    "SAVE_DIR",
#    "GAP_THRESHOLD",
#)
