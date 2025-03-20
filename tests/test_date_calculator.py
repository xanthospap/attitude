# -*- coding: utf-8 -*-

"""Tests for date_calculator."""

import datetime
import pytest

from date_calculator import DateCalculator
from exceptions import FutureDateError, UnsupportedYearError


invalid_past_dates = [
    '2014-01-09', '2014 01 09', '2014/01/09',
    '2014-01-9', '2014 01 9', '2014/01/9',
    '2014-1-09', '2014 1 09', '2014/1/09',
    '2014-1-9', '2014 1 9', '2014/1/9',
    '09-01-2014', '09 01 2014', '09/01/2014',
    '9-01-2014', '9 01 2014', '9/01/2014',
    '09-1-2014', '09 1 2014', '09/1/2014',
    '9-1-2014', '9 1 2014', '9/1/2014',

    '2000-01-01',
    '2000-01-1',
    '31-12-1999',
    '4-3-1999',
    '20-12-1970'
]

valid_dates = [
    ('2021-09-03', datetime.date(2021, 9, 3)),
    ('2021 09 03', datetime.date(2021, 9, 3)),
    ('2021/09/03', datetime.date(2021, 9, 3)),
    ('2021-09-3', datetime.date(2021, 9, 3)),
    ('2021 09 3', datetime.date(2021, 9, 3)),
    ('2021/09/3', datetime.date(2021, 9, 3)),
    ('2021-9-03', datetime.date(2021, 9, 3)),
    ('2021 9 03', datetime.date(2021, 9, 3)),
    ('2021/9/03', datetime.date(2021, 9, 3)),
    ('2021-9-3', datetime.date(2021, 9, 3)),
    ('2021 9 3', datetime.date(2021, 9, 3)),
    ('2021/9/3', datetime.date(2021, 9, 3)),
    ('03-09-2021', datetime.date(2021, 9, 3)),
    ('03 09 2021', datetime.date(2021, 9, 3)),
    ('03/09/2021', datetime.date(2021, 9, 3)),
    ('3-09-2021', datetime.date(2021, 9, 3)),
    ('3 09 2021', datetime.date(2021, 9, 3)),
    ('3/09/2021', datetime.date(2021, 9, 3)),
    ('03-9-2021', datetime.date(2021, 9, 3)),
    ('03 9 2021', datetime.date(2021, 9, 3)),
    ('03/9/2021', datetime.date(2021, 9, 3)),
    ('3-9-2021', datetime.date(2021, 9, 3)),
    ('3 9 2021', datetime.date(2021, 9, 3)),
    ('3/9/2021', datetime.date(2021, 9, 3)),

    ('2017 12 17', datetime.date(2017, 12, 17)),
    ('17 12 2017', datetime.date(2017, 12, 17)),
    ('17-12-2017', datetime.date(2017, 12, 17)),
    ('12-17-2017', datetime.date(2017, 12, 17)),
    ('2021 12 31', datetime.date(2021, 12, 31)),
    ('3 9 2019', datetime.date(2019, 9, 3)),
    ('9 03 2019', datetime.date(2019, 3, 9))
]

valid_ranges = [
    ('10-05-2023', [[datetime.date(2023, 5, 5),
                     datetime.date(2023, 5, 6),
                     datetime.date(2023, 5, 7),
                     datetime.date(2023, 5, 8),
                     datetime.date(2023, 5, 9),
                     datetime.date(2023, 5, 10),
                     datetime.date(2023, 5, 11),
                     datetime.date(2023, 5, 12),
                     datetime.date(2023, 5, 13)]]),
    ('31-12-2023', [[datetime.date(2023, 12, 29),
                     datetime.date(2023, 12, 30),
                     datetime.date(2023, 12, 31)],
                    [datetime.date(2024, 1, 1),
                     datetime.date(2024, 1, 2),
                     datetime.date(2024, 1, 3),
                     datetime.date(2024, 1, 4),
                     datetime.date(2024, 1, 5),
                     datetime.date(2024, 1, 6)]])
]

def test_future_date_failure():
    with pytest.raises(FutureDateError):
        _ = DateCalculator('2100 01 1')

@pytest.mark.parametrize('date', invalid_past_dates)
def test_cutoff_date_failure(date):
    with pytest.raises(UnsupportedYearError):
        _ = DateCalculator(date)

@pytest.mark.parametrize('given,expected', valid_dates)
def test_instantiate_success(given, expected):
    calculator = DateCalculator(given)
    assert calculator._parsed_date == expected

@pytest.mark.parametrize('given,expected', valid_ranges)
def test_calculate_ranges(given, expected):
    calculator = DateCalculator(given)
    assert calculator.date_ranges == expected
