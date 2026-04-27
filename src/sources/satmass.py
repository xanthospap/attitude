from __future__ import annotations


IDS_SATMASS_BASE_URL = "ftp://ftp.ids-doris.org/pub/ids/satellites"


def satmass_filename(satellite: str) -> str:
    """
    Return the IDS satellite mass filename.

    Example:
        ja3 -> ja3mass.txt
    """

    return f"{satellite.lower()}mass.txt"


def satmass_url(
    satellite: str,
    base_url: str = IDS_SATMASS_BASE_URL,
) -> str:
    """
    Return the IDS URL for a satellite mass file.

    Example:
        ja3 -> ftp://ftp.ids-doris.org/pub/ids/satellites/ja3mass.txt
    """

    return f"{base_url.rstrip('/')}/{satmass_filename(satellite)}"
