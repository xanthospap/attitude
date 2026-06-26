from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET

import pandas as pd


QUATERNION_XML_SUFFIXES = (".eef", ".xml")
ARCHIVE_SUFFIXES = (".tgz", ".tar", ".tar.gz")


def _local_name(tag: str) -> str:
    """Return an XML tag name without its namespace, if present."""

    return tag.rsplit("}", 1)[-1]


def _children_by_local_name(element: ET.Element) -> dict[str, ET.Element]:
    return {_local_name(child.tag): child for child in list(element)}


def _required_child_text(element: ET.Element, child_name: str) -> str:
    children = _children_by_local_name(element)

    try:
        child = children[child_name]
    except KeyError as exc:
        raise ValueError(f"Missing CryoSat quaternion XML tag {child_name!r}") from exc

    if child.text is None:
        raise ValueError(f"Empty CryoSat quaternion XML tag {child_name!r}")

    return child.text.strip()


def _parse_tai_timestamp(value: str) -> datetime:
    """
    Parse CryoSat quaternion timestamps.

    The specification uses values such as:
        TAI=2019-11-02T21:55:23.000000
    """

    value = value.strip()

    if "=" in value:
        reference, value = value.split("=", 1)
        if reference.strip().upper() != "TAI":
            raise ValueError(f"Unsupported CryoSat time reference {reference!r}")

    value = value.rstrip("Z")

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    raise ValueError(f"Unsupported CryoSat timestamp: {value!r}")


def _is_quaternion_xml_member(name: str) -> bool:
    name = Path(name).name.lower()
    return name.endswith(QUATERNION_XML_SUFFIXES)


def _read_xml_bytes(path: Path) -> bytes:
    """Read a CryoSat .EEF XML file, directly or from a .TGZ/.tar archive."""

    lower_name = path.name.lower()

    if lower_name.endswith(ARCHIVE_SUFFIXES):
        with tarfile.open(path, "r:*") as archive:
            candidates = [
                member
                for member in archive.getmembers()
                if member.isfile() and _is_quaternion_xml_member(member.name)
            ]

            if not candidates:
                raise ValueError(f"No .EEF/.xml file found inside CryoSat archive {path}")

            # Prefer the normal CryoSat Earth Explorer payload when more than one
            # XML-like member is present.
            candidates.sort(
                key=lambda member: (
                    not Path(member.name).name.upper().endswith(".EEF"),
                    Path(member.name).name,
                )
            )
            member = candidates[0]
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Could not read {member.name} from CryoSat archive {path}")
            return stream.read()

    return path.read_bytes()


def read_cryosat_quaternion_file(path: str | Path) -> pd.DataFrame:
    """
    Read a CryoSat-2 AUX_PROQUA file.

    The CryoSat product stores quaternions as vector-first Q1/Q2/Q3 and scalar
    Q4.  The project preprocessor uses scalar-first q0/q1/q2/q3, so this reader
    maps Q4 -> q0 and Q1/Q2/Q3 -> q1/q2/q3.

    Returns a dataframe with columns:
        date_time, q0, q1, q2, q3
    """

    path = Path(path)
    root = ET.fromstring(_read_xml_bytes(path))

    rows: list[dict[str, object]] = []

    for element in root.iter():
        if _local_name(element.tag) != "Quaternions":
            continue

        q1 = float(_required_child_text(element, "Q1"))
        q2 = float(_required_child_text(element, "Q2"))
        q3 = float(_required_child_text(element, "Q3"))
        q4 = float(_required_child_text(element, "Q4"))
        time = _parse_tai_timestamp(_required_child_text(element, "Time"))

        rows.append(
            {
                "date_time": time,
                "q0": q4,
                "q1": q1,
                "q2": q2,
                "q3": q3,
            }
        )

    if not rows:
        raise ValueError(f"No CryoSat quaternion records found in {path}")

    return pd.DataFrame.from_records(rows, columns=["date_time", "q0", "q1", "q2", "q3"])
