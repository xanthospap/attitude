# -*- coding: utf-8 -*-

"""Configuration module."""

# NOTE:
# Maximum allowed gap in seconds (for Sentinel satellites mostly).
# Interpolate if exceeded.
GAP_THRESHOLD = 10

# ***

SATELLITE_INFO = {
    "ja1": {
        "name": "Jason-1",
        "launch_year": 2001,
        "base_url": "https://cddis.nasa.gov/archive/doris/ancillary/quaternions",
        "data_types": ["qbody", "qsolp"],
    },
    "ja2": {
        "name": "Jason-2",
        "launch_year": 2008,
        "base_url": "https://cddis.nasa.gov/archive/doris/ancillary/quaternions",
        "data_types": ["qbody", "qsolp"],
    },
    "ja3": {
        "name": "Jason-3",
        "launch_year": 2016,
        "base_url": "https://cddis.nasa.gov/archive/doris/ancillary/quaternions",
        "data_types": ["qbody", "qsolp"],
    },
    "s3a": {
        "name": "Sentinel-3A",
        "launch_year": 2016,
        "base_url": "Sentinel-3/AUX/AUX_PROQUA",
        "data_types": ["qbody"],
    },
    "s3b": {
        "name": "Sentinel-3B",
        "launch_year": 2018,
        "base_url": "Sentinel-3/AUX/AUX_PROQUA",
        "data_types": ["qbody"],
    },
    "s6a": {
        "name": "Sentinel-6A",
        "launch_year": 2020,
        "base_url": "Sentinel-6/AUX/AUX_PROQUA",
        "data_types": ["qbody"],
    },
}


def CUTOFF_YEAR(satellite):
    return SATELLITE_INFO[satellite]["launch_year"]
