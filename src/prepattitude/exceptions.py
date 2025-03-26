# -*- coding: utf-8 -*-

"""Exceptions module."""


class FutureDateError(Exception):
    """Parser does not suport future dates."""


class UnsupportedYearError(Exception):
    """Parser does not suport years before CUTOFF_YEAR."""


__all__ = (
    "FutureDateError",
    "UnsupportedYearError"
)
