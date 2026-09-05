"""Generic "export this table to PDF" helper — a printable, tax/records-
style report companion to ui/csv_export.py's CSV export. Uses Qt's own
QtPrintSupport rather than a new dependency (PIL/matplotlib/reportlab are
already excluded from the build; see PokerForge.spec) — QTextDocument
renders a small HTML table and QPrinter prints straight to a PDF file,
no actual printer involved."""
import html

from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QTextDocument
from PyQt6.QtPrintSupport import QPrinter

from ui.csv_export import _cell_text


def _build_html(table, title: str, subtitle: str) -> str:
    headers = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else ''
               for c in range(table.columnCount())]
    header_html = ''.join(f"<th>{html.escape(h)}</th>" for h in headers)

    rows_html = []
    for r in range(table.rowCount()):
        cells = ''.join(f"<td>{html.escape(_cell_text(table, r, c))}</td>"
                         for c in range(table.columnCount()))
        rows_html.append(f"<tr>{cells}</tr>")

    return f"""<html><head><style>
        body {{ font-family: Arial, sans-serif; color: #111; }}
        h1 {{ font-size: 18px; margin-bottom: 2px; }}
        h2 {{ font-size: 12px; color: #555; font-weight: normal; margin-top: 0; margin-bottom: 16px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: center; font-size: 11px; }}
        th {{ background: #eee; }}
        tr:nth-child(even) {{ background: #f7f7f7; }}
    </style></head><body>
        <h1>{html.escape(title)}</h1>
        <h2>{html.escape(subtitle)}</h2>
        <table><tr>{header_html}</tr>{''.join(rows_html)}</table>
    </body></html>"""


def export_table_to_pdf(table, parent, title: str, subtitle: str = "",
                         default_filename: str = "export.pdf") -> bool:
    """Prompts for a save location and prints `table` (headers + every
    row, exactly like export_table_to_csv) as a formatted PDF, with
    `title`/`subtitle` as a header block above it. Shows a confirmation
    or error message box itself. Returns True iff a file was written."""
    path, _ = QFileDialog.getSaveFileName(parent, "Export to PDF", default_filename, "PDF Files (*.pdf)")
    if not path:
        return False

    try:
        doc = QTextDocument()
        doc.setHtml(_build_html(table, title, subtitle))
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        doc.print(printer)
    except OSError as exc:
        QMessageBox.warning(parent, "Export Failed", f"Couldn't write the file:\n{exc}")
        return False
    QMessageBox.information(parent, "Export Complete", f"Exported {table.rowCount()} row(s) to:\n{path}")
    return True
