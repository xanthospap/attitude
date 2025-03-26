# -*- coding: utf-8 -*-

"""date_utils.py

Various date handling utilities.
"""

import datetime
import logging
from dataclasses import dataclass

# import arrow

from prepattitude.configuration import CUTOFF_YEAR
from prepattitude.exceptions import FutureDateError, UnsupportedYearError


LOGGING_LEVEL = logging.INFO
# LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style="{",
    format="{levelname}: {name} ({funcName}) [{lineno}]:  {message}",
)


@dataclass
class DateCalculator:
    """Miscelaneous date handling utilities."""

    _reference_date: datetime.datetime
    _logger = None

    def __post_init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _calculate_range(reference_date: datetime.date) -> list[datetime.date]:
        """Find the "extended" week that contains the reference date."""
        # day difference of start of the "extended" week, depending on the weekday of the reference
        # date;  method datetime.date.weekday() returns 0 for Mon, 1 for Tue, etc.
        day_difference = {
            0: -3,
            1: -4,
            2: -5,
            3: -6,
            4: -7,
            5: -8,
            6: -2,
        }  # 0: Mon, ..., 6: Sun

        # begining of the "extended" week; Fri of the previous week
        begin_week = reference_date + datetime.timedelta(
            days=day_difference[reference_date.weekday()]
        )

        # add the next 8 days; until Sat of the current week (data until Mon of the following week)
        return [begin_week + datetime.timedelta(days=d) for d in range(9)]

    @staticmethod
    def _wrap_around_year(date_range: list[datetime.date]) -> list[list[datetime.date]]:
        """Split the date list in two if the "extended" week ends in a different year."""
        # years that 'date_range' spans
        # years = sorted(list(set([d.year for d in date_range])))
        years = sorted({d.year for d in date_range})

        result = []
        for y in years:
            result.append([d for d in date_range if d.year == y])

        return result

    @property
    def date_ranges(self) -> list[list[datetime.date]]:
        """List of date range(s)."""
        return self._wrap_around_year(self._calculate_range(self._reference_date))
