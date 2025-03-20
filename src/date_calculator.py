# -*- coding: utf-8 -*-

"""date_utils.py

Various date handling utilities.
"""

import datetime
import logging
from dataclasses import dataclass

import arrow

from configuration import CUTOFF_YEAR
from exceptions import FutureDateError, UnsupportedYearError


LOGGING_LEVEL = logging.INFO
# LOGGING_LEVEL = logging.DEBUG  # try logging.DEBUG for more info

logging.basicConfig(
    level=LOGGING_LEVEL,
    style='{',
    format='{levelname}: {name} ({funcName}) [{lineno}]:  {message}'
)

DATE_FORMATS = [
    'YYYY-MM-DD', 'YYYY-MM-D', 'YYYY-M-DD', 'YYYY-M-D',
    'YYYY MM DD', 'YYYY MM D', 'YYYY M DD', 'YYYY M D',
    'YYYY/MM/DD', 'YYYY/MM/D', 'YYYY/M/DD', 'YYYY/M/D',
    'DD-MM-YYYY', 'D-MM-YYYY', 'DD-M-YYYY', 'D-M-YYYY',
    'DD MM YYYY', 'D MM YYYY', 'DD M YYYY', 'D M YYYY',
    'DD/MM/YYYY', 'D/MM/YYYY', 'DD/M/YYYY', 'D/M/YYYY',
]


@dataclass
class DateCalculator:
    """Miscelaneous date handling utilities."""
    _reference_date: str
    _parsed_date = None
    _logger = None

    def __post_init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._validate_date()

    def _validate_date(self):
        """Parse the reference date and test its validity."""
        try:
            parsed_date = arrow.get(self._reference_date, DATE_FORMATS).date()
        except arrow.ParserError:
            self._logger.error(f'Invalid date string: {self._reference_date}.')
            raise

        if parsed_date > datetime.date.today():
            raise FutureDateError(self._reference_date)

        if parsed_date.year < CUTOFF_YEAR:
            raise UnsupportedYearError(parsed_date.year)

        self._parsed_date = parsed_date

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
        begin_week = reference_date + \
            datetime.timedelta(days=day_difference[reference_date.weekday()])

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
        return self._wrap_around_year(self._calculate_range(self._parsed_date))
