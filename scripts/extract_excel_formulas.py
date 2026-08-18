"""
Extract sheet names, formulas, and labelled numeric values from Excel reference
files. Handles both .xlsx (openpyxl, full formula strings) and .xls (xlrd,
cached values only — formula strings are not stored in the binary .xls format).
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
REF_DIR = ROOT / "data" / "reference"

FILES = [
    REF_DIR / "philippe_2010_sizing.xls",
    REF_DIR / "390geothermal_calc.xlsx",
]

OUTPUT = REF_DIR / "formulas_dump.txt"

lines = []


def emit(s=""):
    lines.append(s)
    print(s)


# ---------------------------------------------------------------------------
# .xlsx via openpyxl
# ---------------------------------------------------------------------------

def process_xlsx(path: pathlib.Path):
    import openpyxl

    emit(f"\n{'='*70}")
    emit(f"FILE: {path.name}  [format: xlsx — formula strings available]")
    emit(f"{'='*70}")

    wb = openpyxl.load_workbook(path, data_only=False)
    emit(f"\nSheets: {wb.sheetnames}\n")

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        emit(f"\n--- Sheet: {sheet_name} ---")

        # Pass 1: formulas
        emit("\n  [Formulas]")
        found_formulas = False
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                if isinstance(val, str) and val.startswith("="):
                    emit(f"  {sheet_name}!{cell.coordinate}  {val}")
                    found_formulas = True
        if not found_formulas:
            emit("  (none)")

        # Pass 2: labelled numeric values
        emit("\n  [Labelled numeric values]")
        found_values = False
        rows_list = list(ws.iter_rows())
        for row in rows_list:
            for i, cell in enumerate(row):
                val = cell.value
                if not isinstance(val, (int, float)):
                    continue
                # check left neighbour
                label = None
                if i > 0:
                    left = row[i - 1].value
                    if isinstance(left, str) and left.strip():
                        label = left.strip()
                # check right neighbour as fallback
                if label is None and i < len(row) - 1:
                    right = row[i + 1].value
                    if isinstance(right, str) and right.strip():
                        label = right.strip()
                if label:
                    emit(f"  {sheet_name}!{cell.coordinate}  label='{label}'  value={val}")
                    found_values = True
        if not found_values:
            emit("  (none)")


# ---------------------------------------------------------------------------
# .xls via xlrd
# ---------------------------------------------------------------------------

def process_xls(path: pathlib.Path):
    import xlrd

    emit(f"\n{'='*70}")
    emit(f"FILE: {path.name}  [format: xls — cached values only, no formula strings]")
    emit(f"{'='*70}")

    wb = xlrd.open_workbook(str(path), formatting_info=False)
    emit(f"\nSheets: {wb.sheet_names()}\n")

    for sheet_name in wb.sheet_names():
        ws = wb.sheet_by_name(sheet_name)
        emit(f"\n--- Sheet: {sheet_name} ---")

        # xlrd XL_CELL_* types: 0=empty, 1=text, 2=number, 3=date, 4=bool, 5=error, 6=blank
        XL_CELL_TEXT   = 1
        XL_CELL_NUMBER = 2

        # Pass 1: cells containing formulas (xlrd exposes cached result, not formula)
        #   We flag number cells whose formula flag bit is set via cell_xf_index but
        #   xlrd doesn't expose formula strings — note this limitation clearly.
        emit("\n  [Formulas] — not extractable from .xls binary format; see cached values below")

        # Pass 2: labelled numeric values
        emit("\n  [Labelled numeric values]")
        found_values = False
        for r in range(ws.nrows):
            row_types  = ws.row_types(r)
            row_values = ws.row_values(r)
            for c in range(ws.ncols):
                if row_types[c] != XL_CELL_NUMBER:
                    continue
                val = row_values[c]
                label = None
                if c > 0 and row_types[c - 1] == XL_CELL_TEXT:
                    text = str(row_values[c - 1]).strip()
                    if text:
                        label = text
                if label is None and c < ws.ncols - 1 and row_types[c + 1] == XL_CELL_TEXT:
                    text = str(row_values[c + 1]).strip()
                    if text:
                        label = text
                if label:
                    addr = f"{xlrd.colname(c)}{r + 1}"
                    emit(f"  {sheet_name}!{addr}  label='{label}'  value={val}")
                    found_values = True
        if not found_values:
            emit("  (none)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

emit("EXCEL FORMULA / VALUE DUMP")
emit(f"Reference directory: {REF_DIR}")

for fpath in FILES:
    if not fpath.exists():
        emit(f"\nWARNING: {fpath.name} not found — skipping")
        continue
    if fpath.suffix.lower() == ".xlsx":
        process_xlsx(fpath)
    elif fpath.suffix.lower() == ".xls":
        process_xls(fpath)
    else:
        emit(f"\nWARNING: {fpath.name} — unknown extension, skipping")

emit(f"\n\nDone. Output also saved to: {OUTPUT}")
OUTPUT.write_text("\n".join(lines) + "\n")
