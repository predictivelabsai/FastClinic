"""Dependency-free .xlsx reader (stdlib zipfile + ElementTree).

The clinic PMS export is a plain OOXML workbook. The venv has no pandas/openpyxl
and no pip, so we parse the sheets ourselves. Cells are addressed by their
spreadsheet reference (A1, C2, …) — empty cells are omitted from a row, so we
MUST key on the column letter, not positional order.
"""
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NSMAP = {"m": _NS[1:-1]}
_EPOCH = date(1899, 12, 30)  # Excel's serial-date origin (with the 1900 leap bug)
_EPOCH_DT = datetime(1899, 12, 30)


def _col_index(ref: str) -> int:
    """'C2' -> 2 (zero-based column index)."""
    letters = "".join(c for c in (ref or "") if c.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.findall("m:si", _NSMAP):
        out.append("".join(t.text or "" for t in si.iter(_NS + "t")))
    return out


def sheet_names(path: str) -> list[str]:
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        return [s.get("name") for s in wb.iter(_NS + "sheet")]


def read_sheet(path: str, index: int) -> list[dict]:
    """Read worksheet `index` (1-based) into a list of {header: value} dicts.

    Values are returned as raw strings (or None for blanks). Date conversion is
    left to the caller via `excel_date`, since only some columns are dates.
    """
    with zipfile.ZipFile(path) as z:
        ss = _shared_strings(z)
        sx = ET.fromstring(z.read(f"xl/worksheets/sheet{index}.xml"))
        rows = sx.findall(".//m:sheetData/m:row", _NSMAP)
        table = []
        for r in rows:
            cells: dict[int, str] = {}
            for c in r.findall("m:c", _NSMAP):
                ci = _col_index(c.get("r"))
                v = c.find("m:v", _NSMAP)
                val = v.text if v is not None else None
                if c.get("t") == "s" and val is not None:
                    val = ss[int(val)]
                cells[ci] = val
            table.append(cells)
        if not table:
            return []
        header = table[0]
        width = max(header) + 1
        names = [header.get(i) or f"col{i}" for i in range(width)]
        out = []
        for row in table[1:]:
            out.append({names[i]: row.get(i) for i in range(width)})
        return out


def excel_date(v) -> str | None:
    """Convert an Excel serial (e.g. '45071.38…') to an ISO date string."""
    if v in (None, "", "NULL"):
        return None
    try:
        return (_EPOCH + timedelta(days=float(v))).isoformat()
    except (ValueError, TypeError):
        return None


def excel_datetime(v) -> str | None:
    """Convert an Excel serial to an ISO datetime string (keeps the time part)."""
    if v in (None, "", "NULL"):
        return None
    try:
        dt = _EPOCH_DT + timedelta(days=float(v))
        return dt.isoformat(sep=" ", timespec="seconds")
    except (ValueError, TypeError):
        return None
