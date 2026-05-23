"""Reader for SINEX_TRO v2.00 tropospheric zenith time series.

This module intentionally has no third-party dependencies.  It implements a
small, focused reader for the parts of the SINEX_TRO v2.00 format needed to
extract zenith-direction tropospheric parameters from the ``TROP/SOLUTION``
block.  It also accepts the older/NGL-style ``%=TRO 1.00`` files that describe
solution columns with ``SOLUTION_FIELDS_1``/``SOLUTION_FIELDS_2`` or only with
the comment header above ``TROP/SOLUTION``.

Public API
==========

    ts = TropoSinex("GOP2OPSFIN_20131680000_01D_05M_TRO.TRO")
    ztd = ts.get("GOPE00CZE", "TROTOT", "2013:168:00000", "2013:169:00000")

``get(...)`` returns a list of ``(datetime, value)`` pairs.  Numeric values are
returned in the parameter's base unit, because the SINEX_TRO specification says
that values in ``TROP/SOLUTION`` must be divided by the corresponding
``TROPO PARAMETER UNITS`` entry.

Supported ``parameter_name`` values are the Table 1 zenith-direction
parameter acronyms from SINEX_TRO v2.00:

    TROTOT, TROWET, TRODRY, TGNTOT, TGNWET, TGNDRY,
    TGETOT, TGEWET, TGEDRY, STDDEV, IWV

A note about ``STDDEV``
----------------------

SINEX_TRO uses the name ``STDDEV`` as a generic column name for "standard
deviation of the preceding estimated value".  A file can therefore contain more
than one ``STDDEV`` column.  For all ordinary parameter names, ``get`` returns
``list[tuple[datetime, float | None]]``.  For ``STDDEV``, ``get`` returns
``list[tuple[datetime, dict[str, float | None]]]`` where the dictionary maps
the parameter to which each standard deviation belongs, for example::

    [(datetime(2013, 6, 17, 17, 55), {"TROTOT": 0.0053,
                                      "TGNTOT": 0.00085,
                                      "TGETOT": 0.00093})]

Missing numeric values, represented in SINEX_TRO as -999 or -999.000 before
unit scaling, are returned as ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple, Union
from contextlib import contextmanager
import gzip
import re


Number = Union[int, float]
DateLike = Union[str, date, datetime]
SingleValue = Optional[float]
StddevValue = Dict[str, Optional[float]]
TimeSeries = List[Tuple[datetime, Union[SingleValue, StddevValue]]]


@dataclass(frozen=True)
class _TropSolutionRow:
    """One parsed row from the TROP/SOLUTION block.

    Attributes
    ----------
    site:
        Station marker/site code, normalized to upper case.  SINEX_TRO v2.00
        allows the RINEX-3-style 9-character Site Code and, for backward
        compatibility, left-aligned 4-character station codes.
    epoch:
        The epoch of the solution, converted from ``YYYY:DOY:SOD`` to a Python
        ``datetime``.  The object is timezone-naive because the file's time
        system is declared separately in ``TROP/DESCRIPTION`` (usually ``G`` or
        ``UTC``); this reader does not transform between time systems.
    values:
        Values from the row, already converted to the base units declared by
        SINEX_TRO Table 1/2/3 via ``raw_value / TROPO_PARAMETER_UNIT``.  Missing
        numeric values are stored as ``None``.
    """

    site: str
    epoch: datetime
    values: Tuple[Optional[float], ...]


class TropoSinex:
    """Read zenith tropospheric parameter time series from a SINEX_TRO file.

    Parameters
    ----------
    tropospheric_sinex_filename:
        Path to a SINEX_TRO text file.  ``.gz`` files are supported
        transparently.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If mandatory information needed to parse ``TROP/SOLUTION`` is absent or
        inconsistent.

    Notes
    -----
    The reader focuses on the mandatory ``TROP/DESCRIPTION`` and
    ``TROP/SOLUTION`` blocks for zenith-direction values.  It ignores slant
    solution data and most metadata blocks, but keeps useful metadata such as
    the time system and the list of available sites.
    """

    # Table 1: Tropospheric parameter types in zenith direction, SINEX_TRO v2.00.
    TABLE1_PARAMETERS = frozenset(
        {
            "TROTOT",  # tropospheric zenith total delay (ZTD)
            "TROWET",  # tropospheric zenith wet delay (ZWD)
            "TRODRY",  # tropospheric zenith dry/hydrostatic delay (ZHD)
            "TGNTOT",  # total gradient - North component
            "TGNWET",  # North gradient component; Table 1 acronym
            "TGNDRY",  # North gradient component; Table 1 acronym
            "TGETOT",  # total gradient - East component
            "TGEWET",  # wet gradient - East component
            "TGEDRY",  # dry gradient - East component
            "STDDEV",  # standard deviation for the preceding estimated value
            "IWV",     # integrated water vapour
        }
    )

    # SINEX_TRO v2.00 examples usually use YYYY:DOY:SOD, whereas older
    # SINEX_TRO/NGL files often use YY:DOY:SOD (for example 20:001:00000).
    _SINEX_EPOCH_RE = re.compile(r"^(?P<year>\d{2}|\d{4}):(?P<doy>\d{3}):(?P<sod>\d{1,5})$")

    # Non-standard aliases commonly seen in older/NGL tropo SINEX files.
    # The public API remains Table-1 oriented, so aliases are normalized to
    # canonical names whenever possible.
    _PARAMETER_ALIASES = {
        "TRWET": "TROWET",
        "WVAPOR": "IWV",
        "PWV": "IWV",
        "WMTEMP": "WMTEMP",
        "MTEMP": "WMTEMP",
        "_SIG": "STDDEV",
        "SIG": "STDDEV",
        "SIGMA": "STDDEV",
    }
    _KNOWN_DESCRIPTION_KEYS = (
        "TROPO PARAMETER NAMES",
        "TROPO PARAMETER UNITS",
        "TROPO PARAMETER WIDTH",
        "SLANT PARAMETER NAMES",
        "SLANT PARAMETER UNITS",
        "SLANT PARAMETER WIDTH",
        "DATA SAMPLING INTERVAL",
        "TROPO MODELING METHOD",
        "GNSS SYSTEMS",
        "TIME SYSTEM",
        "REFRACTIVITY COEFFICIENTS",
        "SOURCE OF MET/DATA",
        "OCEAN TIDE LOADING MODEL",
        "ATMOSPH TIDE LOADING MODEL",
        "GEOID MODEL",
        "TROPO SAMPLING INTERVAL",
        "SLANT SAMPLING INTERVAL",
        "A PRIORI TROPOSPHERE",
        "TROPO MAPPING FUNCTION",
        "GRADS MAPPING FUNCTION",
        "ELEVATION CUTOFF ANGLE",
        "OBSERVATION WEIGHTING",
        "OBSERVATION WEITHING",  # typo found in some documents/files
        "BIAS FROM INTERVAL",
        "DELETE FACTOR",
        # Older/NGL-style SINEX_TRO 1.00 keys.
        "SAMPLING INTERVAL",
        "SAMPLING TROP",
        "CONVERSION FACTORS",
        "SOLUTION_FIELDS_1",
        "SOLUTION_FIELDS_2",
        "SOLUTION_FIELDS_3",
        "SOLUTION_FIELDS_4",
        "SOLUTION_FIELDS_5",
    )

    def __init__(self, tropospheric_sinex_filename: Union[str, Path]) -> None:
        self.path = Path(tropospheric_sinex_filename)
        if not self.path.exists():
            raise FileNotFoundError(str(self.path))

        # Public-ish metadata populated by _parse().
        self.time_system: Optional[str] = None
        self.tropo_parameter_names: Tuple[str, ...] = ()
        self.tropo_parameter_units: Tuple[float, ...] = ()
        self.tropo_parameter_widths: Tuple[int, ...] = ()

        # Internal indexes populated by _parse().
        self._rows_by_site: Dict[str, List[_TropSolutionRow]] = {}
        self._columns_by_parameter: Dict[str, List[int]] = {}
        self._stddev_owner_by_column: Dict[int, str] = {}

        self._parse()

    def get(self, site: str, parameter_name: str, date_from: DateLike, date_to: DateLike) -> TimeSeries:
        """Return a parameter time series for one site in ``[date_from, date_to)``.

        Parameters
        ----------
        site:
            Station name / marker.  The 9-character Site Code is expected for
            SINEX_TRO v2.00 files, but 4-character legacy station names are
            also handled if present in the file.  Matching is case-insensitive.
        parameter_name:
            One of the Table 1 zenith-direction parameter acronyms:
            ``TROTOT``, ``TROWET``, ``TRODRY``, ``TGNTOT``, ``TGNWET``,
            ``TGNDRY``, ``TGETOT``, ``TGEWET``, ``TGEDRY``, ``STDDEV``,
            or ``IWV``.
        date_from:
            Inclusive start time.  Accepted forms are:

            * ``datetime``
            * ``date`` (interpreted as midnight)
            * ISO-8601 string, e.g. ``"2013-06-17T18:00:00"``
            * SINEX_TRO epoch string, e.g. ``"2013:168:64800"``

        date_to:
            Exclusive end time, with the same accepted forms as ``date_from``.

        Returns
        -------
        list[tuple[datetime, float | None]]
            For ordinary parameters, a list of ``(epoch, value)`` pairs.  Values
            are in base units.  Missing values are ``None``.
        list[tuple[datetime, dict[str, float | None]]]
            For ``STDDEV``, the second item is a dictionary mapping the preceding
            parameter name to its standard deviation value.

        Raises
        ------
        ValueError
            If the parameter name is not in SINEX_TRO Table 1, or the requested
            time interval is invalid.
        KeyError
            If the site or parameter is valid but absent from this file.
        """

        normalized_site = self._resolve_site(site)
        parameter = self._canonical_parameter_name(parameter_name)
        start = self._coerce_datetime(date_from)
        stop = self._coerce_datetime(date_to)

        if start >= stop:
            raise ValueError("date_from must be earlier than date_to")
        if parameter not in self.TABLE1_PARAMETERS:
            allowed = ", ".join(sorted(self.TABLE1_PARAMETERS))
            raise ValueError(f"Unsupported Table 1 parameter {parameter_name!r}. Allowed values: {allowed}")
        if normalized_site not in self._rows_by_site:
            raise KeyError(f"Site {site!r} was not found in {self.path.name}")
        if parameter not in self._columns_by_parameter:
            present = ", ".join(self.available_parameters())
            raise KeyError(f"Parameter {parameter!r} is not present in {self.path.name}. Present: {present}")

        columns = self._columns_by_parameter[parameter]
        rows = self._rows_by_site[normalized_site]
        result: TimeSeries = []

        if parameter == "STDDEV":
            # STDDEV may occur multiple times, and each occurrence belongs to
            # the estimated value immediately preceding it.  Return all of them
            # for each epoch so no information is silently discarded.
            for row in rows:
                if start <= row.epoch < stop:
                    by_owner: Dict[str, Optional[float]] = {}
                    for col in columns:
                        owner = self._stddev_owner_by_column.get(col, f"STDDEV#{col + 1}")
                        # Avoid overwriting if a non-standard file repeats an
                        # owner name.  Keep keys predictable and readable.
                        key = owner
                        n = 2
                        while key in by_owner:
                            key = f"{owner}#{n}"
                            n += 1
                        by_owner[key] = row.values[col]
                    result.append((row.epoch, by_owner))
            return result

        # For Table 1 names other than STDDEV, a duplicate name would be unusual
        # but not impossible in a malformed or extended file.  We choose the
        # first occurrence and make the behavior deterministic.
        column = columns[0]
        for row in rows:
            if start <= row.epoch < stop:
                result.append((row.epoch, row.values[column]))
        return result

    def available_sites(self) -> Tuple[str, ...]:
        """Return site codes that have at least one ``TROP/SOLUTION`` row."""

        return tuple(sorted(self._rows_by_site))

    def available_parameters(self) -> Tuple[str, ...]:
        """Return parameter column names present in this file's TROP/SOLUTION.

        Duplicate column names such as ``STDDEV`` are returned only once.
        """

        return tuple(self._columns_by_parameter.keys())

    def parameter_columns(self) -> Mapping[str, Tuple[int, ...]]:
        """Return a read-only view of parameter names to zero-based value columns.

        This is mostly useful for diagnostics and for understanding files that
        contain more than one ``STDDEV`` column.
        """

        return {name: tuple(cols) for name, cols in self._columns_by_parameter.items()}

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        """Parse the file into metadata and an in-memory site index."""

        current_block: Optional[str] = None
        description_items: Dict[str, List[str]] = {}
        saw_trop_solution = False
        trop_solution_header_names: Optional[List[str]] = None

        with self._open_text(self.path) as lines:
            for raw_line in lines:
                line = raw_line.rstrip("\n\r")
                if not line:
                    continue

                first = line[0]

                if first == "+":
                    current_block = line[1:].strip().upper()
                    continue
                if first == "-":
                    current_block = None
                    continue

                # Comment/header/footer lines are not data.  A comment directly
                # after +TROP/SOLUTION often repeats the column names; keep it as
                # a fallback only if TROP/DESCRIPTION is incomplete.
                if first in {"*", "%"}:
                    if current_block == "TROP/SOLUTION" and first == "*":
                        maybe_names = self._parse_trop_solution_comment_header(line)
                        if maybe_names:
                            trop_solution_header_names = maybe_names
                    continue

                # SINEX_TRO data lines begin with one blank character.  Be
                # tolerant of files that have leading tabs/spaces after editing.
                if not line[:1].isspace():
                    continue

                if current_block == "TROP/DESCRIPTION":
                    key, values = self._parse_description_line(line)
                    if key:
                        description_items[key] = values
                    continue

                if current_block == "TROP/SOLUTION":
                    if not self.tropo_parameter_names:
                        self._apply_trop_description(description_items, trop_solution_header_names)
                    self._parse_trop_solution_line(line)
                    saw_trop_solution = True
                    continue

        if not saw_trop_solution:
            raise ValueError(f"No TROP/SOLUTION block was found in {self.path}")

        # Sort rows once, so get(...) returns chronological time series even if
        # the file interleaves multiple stations or has unusual ordering.
        for rows in self._rows_by_site.values():
            rows.sort(key=lambda r: r.epoch)

    def _apply_trop_description(
        self,
        description_items: Mapping[str, Sequence[str]],
        fallback_names: Optional[Sequence[str]],
    ) -> None:
        """Finalize TROP/DESCRIPTION metadata before reading solution values.

        Strict SINEX_TRO v2.00 files provide ``TROPO PARAMETER NAMES``.  NGL
        ``%=TRO 1.00`` files instead commonly provide either
        ``SOLUTION_FIELDS_1``/``SOLUTION_FIELDS_2`` or only a comment line above
        ``TROP/SOLUTION``.  This method accepts all three forms and normalizes
        common aliases such as ``TRWET`` -> ``TROWET`` and ``WVAPOR`` -> ``IWV``.
        """

        names = list(description_items.get("TROPO PARAMETER NAMES", ()))

        # The TROP/SOLUTION comment header is closest to the data columns and
        # fixes known NGL inconsistencies such as SOLUTION_FIELDS_1 saying
        # TRODRY while the actual column header and values are TROTOT.
        if not names and fallback_names:
            names = list(fallback_names)

        if not names:
            names = self._solution_fields_from_description(description_items)

        if not names:
            raise ValueError(
                "TROP/DESCRIPTION does not define TROPO PARAMETER NAMES or "
                "SOLUTION_FIELDS_N, and no TROP/SOLUTION comment header could "
                "be used as a fallback."
            )

        names = [self._canonical_parameter_name(name, allow_extended=True) for name in names]

        units_tokens = list(description_items.get("TROPO PARAMETER UNITS", ()))
        widths_tokens = list(description_items.get("TROPO PARAMETER WIDTH", ()))

        # Units are mandatory in the v2.00 spec, but older/NGL files omit them.
        # When absent, use 1.0 so values are returned in the file's native units
        # (for NGL TRO 1.00 this is typically millimetres for delays/gradients).
        if units_tokens:
            units = [self._parse_float_token(tok) for tok in units_tokens]
        else:
            units = [1.0] * len(names)

        if widths_tokens:
            widths = [int(float(tok)) for tok in widths_tokens]
        else:
            widths = []

        if len(units) != len(names):
            raise ValueError(
                "TROPO PARAMETER UNITS has a different length from "
                f"TROPO PARAMETER NAMES ({len(units)} vs {len(names)})."
            )
        if widths and len(widths) != len(names):
            raise ValueError(
                "TROPO PARAMETER WIDTH has a different length from "
                f"TROPO PARAMETER NAMES ({len(widths)} vs {len(names)})."
            )

        self.tropo_parameter_names = tuple(names)
        self.tropo_parameter_units = tuple(units)
        self.tropo_parameter_widths = tuple(widths)
        self.time_system = " ".join(description_items.get("TIME SYSTEM", ())) or None

        columns: Dict[str, List[int]] = {}
        stddev_owner: Dict[int, str] = {}
        for index, name in enumerate(self.tropo_parameter_names):
            columns.setdefault(name, []).append(index)
            if name == "STDDEV" and index > 0:
                stddev_owner[index] = self.tropo_parameter_names[index - 1]

        self._columns_by_parameter = columns
        self._stddev_owner_by_column = stddev_owner

    @classmethod
    @contextmanager
    def _open_text(cls, path: Path) -> Iterator[Iterable[str]]:
        """Open plain text or gzip-compressed SINEX_TRO files.

        The function is intentionally small and local instead of relying on
        external packages.  It yields a text stream opened with ASCII-compatible
        UTF-8 decoding; malformed bytes are replaced so that a stray non-ASCII
        character in a comment does not stop parsing.
        """

        if path.suffix.lower() == ".gz":
            with gzip.open(path, mode="rt", encoding="utf-8", errors="replace") as fh:
                yield fh
        else:
            with path.open(mode="rt", encoding="utf-8", errors="replace") as fh:
                yield fh

    @classmethod
    def _parse_description_line(cls, line: str) -> Tuple[Optional[str], List[str]]:
        """Parse one data line from ``TROP/DESCRIPTION``.

        The formal layout is ``1X,A29`` followed by type-dependent values.  This
        implementation first uses those fixed columns, then falls back to known
        key matching for files whose spacing has been normalized.
        """

        fixed_key = line[1:30].strip().upper()
        fixed_values = line[30:].split()
        if fixed_key in cls._KNOWN_DESCRIPTION_KEYS:
            return fixed_key, fixed_values

        stripped = line.strip()
        upper = stripped.upper()
        for key in sorted(cls._KNOWN_DESCRIPTION_KEYS, key=len, reverse=True):
            if upper == key:
                return key, []
            if upper.startswith(key + " "):
                return key, stripped[len(key):].split()

        # Unknown TROP/DESCRIPTION keys can be valid extensions.  Ignore them;
        # this reader only needs the mandatory parameter-definition fields.
        return None, []

    @staticmethod
    def _parse_trop_solution_comment_header(line: str) -> Optional[List[str]]:
        """Extract parameter names from a ``*SITE ___EPOCH____ ...`` header.

        Older files often decorate the first two labels with underscores
        (``___EPOCH____``) and use ``SITE`` rather than ``STATION``.  Strip that
        decoration before testing the labels.
        """

        tokens = line[1:].split()
        if len(tokens) < 3:
            return None
        first = tokens[0].upper().strip("_")
        second = tokens[1].upper().strip("_")
        if first in {"SITE", "STATION", "STATIONID"} and second.startswith("EPOCH"):
            return [tok.upper() for tok in tokens[2:]]
        return None

    @classmethod
    def _canonical_parameter_name(cls, name: str, *, allow_extended: bool = False) -> str:
        """Normalize common non-standard column aliases to canonical names."""

        canonical = cls._PARAMETER_ALIASES.get(name.upper().strip(), name.upper().strip())
        if allow_extended or canonical in cls.TABLE1_PARAMETERS:
            return canonical
        return canonical

    @staticmethod
    def _solution_fields_from_description(
        description_items: Mapping[str, Sequence[str]]
    ) -> List[str]:
        """Return concatenated SOLUTION_FIELDS_N entries in numeric order."""

        fields: List[str] = []
        keyed_fields = []
        for key in description_items:
            match = re.match(r"SOLUTION_FIELDS_(\d+)$", key)
            if match:
                keyed_fields.append((int(match.group(1)), key))
        for _, key in sorted(keyed_fields):
            fields.extend(description_items[key])
        return fields

    def _resolve_site(self, site: str) -> str:
        """Resolve a user site string to the site code actually present in rows.

        SINEX_TRO v2.00 commonly uses 9-character RINEX-3 station IDs, while
        NGL TRO 1.00 files commonly use only the 4-character marker.  This
        method accepts either form when the match is unambiguous.
        """

        normalized = self._normalize_site(site)
        if normalized in self._rows_by_site:
            return normalized

        four_char = normalized[:4]
        if four_char in self._rows_by_site:
            return four_char

        matches = [candidate for candidate in self._rows_by_site if candidate.startswith(four_char)]
        if len(matches) == 1:
            return matches[0]

        return normalized

    def _parse_trop_solution_line(self, line: str) -> None:
        """Parse one data line from ``TROP/SOLUTION`` and add it to the index."""

        parts = line.split()
        if len(parts) < 2:
            return

        site = self._normalize_site(parts[0])
        epoch = self._parse_sinex_epoch(parts[1])
        raw_values = parts[2:]

        expected = len(self.tropo_parameter_names)
        if len(raw_values) != expected:
            raise ValueError(
                f"TROP/SOLUTION row for site {site!r} at {parts[1]!r} has "
                f"{len(raw_values)} values, expected {expected}."
            )

        values = tuple(
            self._scale_value(raw, unit)
            for raw, unit in zip(raw_values, self.tropo_parameter_units)
        )
        self._rows_by_site.setdefault(site, []).append(_TropSolutionRow(site, epoch, values))

    @classmethod
    def _parse_sinex_epoch(cls, text: str) -> datetime:
        """Convert ``YYYY:DOY:SOD`` or legacy ``YY:DOY:SOD`` to ``datetime``."""

        match = cls._SINEX_EPOCH_RE.match(text.strip())
        if not match:
            raise ValueError(f"Invalid SINEX_TRO epoch {text!r}; expected YYYY:DOY:SOD or YY:DOY:SOD")
        year_text = match.group("year")
        year = int(year_text)
        if len(year_text) == 2:
            # SINEX-style pivot: 80-99 are 1980-1999, 00-79 are 2000-2079.
            year += 1900 if year >= 80 else 2000
        doy = int(match.group("doy"))
        sod = int(match.group("sod"))
        return datetime(year, 1, 1) + timedelta(days=doy - 1, seconds=sod)

    @classmethod
    def _coerce_datetime(cls, value: DateLike) -> datetime:
        """Accept common date/time inputs and return a comparable datetime."""

        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value

        if isinstance(value, date):
            return datetime.combine(value, time.min)

        if isinstance(value, str):
            stripped = value.strip()
            if cls._SINEX_EPOCH_RE.match(stripped):
                return cls._parse_sinex_epoch(stripped)
            iso = stripped.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(iso)
            except ValueError as exc:
                raise ValueError(
                    f"Could not parse date/time {value!r}. Use datetime/date, "
                    "an ISO-8601 string, or a SINEX_TRO YYYY:DOY:SOD string."
                ) from exc
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed

        raise TypeError(
            f"Unsupported date/time object {value!r}. Use datetime/date, an ISO-8601 string, "
            "or a SINEX_TRO YYYY:DOY:SOD string."
        )

    @staticmethod
    def _normalize_site(site: str) -> str:
        """Normalize user/file site codes for matching."""

        if not isinstance(site, str) or not site.strip():
            raise ValueError("site must be a non-empty string")
        return site.strip().upper()

    @classmethod
    def _scale_value(cls, raw: str, unit: float) -> Optional[float]:
        """Convert a raw numeric field to base units, preserving missing values."""

        value = cls._parse_float_token(raw)
        # SINEX_TRO missing values are tested without scaling applied.
        if value == -999 or value == -999.0:
            return None
        if unit == 0:
            raise ValueError("TROPO PARAMETER UNITS contains zero, cannot scale values")
        return value / unit

    @staticmethod
    def _parse_float_token(token: str) -> float:
        """Parse FORTRAN-ish numeric tokens as Python floats."""

        # Some legacy ASCII formats use D exponents.  Python float supports E.
        return float(token.replace("D", "E").replace("d", "E"))


__all__ = ["TropoSinex", "TimeSeries"]
