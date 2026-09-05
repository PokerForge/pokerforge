"""Generic "export this table to CSV" helper — reusable by any QTableWidget
in the app (hand lists, By Position, the villain pool) rather than each
screen reinventing file-save-dialog + row-walking logic."""
import csv

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QLabel


def _cell_text(table, row, col) -> str:
    item = table.item(row, col)
    if item is not None:
        return item.text()
    widget = table.cellWidget(row, col)
    if widget is not None:
        # Card-badge cells (hole cards, flop/turn/river) are QLabels inside
        # a container widget rather than plain QTableWidgetItem text.
        return ' '.join(l.text() for l in widget.findChildren(QLabel))
    return ''


def export_table_to_csv(table, parent, default_filename: str = "export.csv") -> bool:
    """Prompts for a save location and writes every row/column of `table`
    to CSV, headers included. Shows a confirmation or error message box
    itself, so callers don't need to. Returns True iff a file was written."""
    path, _ = QFileDialog.getSaveFileName(parent, "Export to CSV", default_filename, "CSV Files (*.csv)")
    if not path:
        return False
    try:
        # utf-8-sig (BOM) so Excel renders suit glyphs (♠♥♦♣) and currency
        # symbols (£/€) correctly instead of as mojibake.
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            headers = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else ''
                       for c in range(table.columnCount())]
            writer.writerow(headers)
            for r in range(table.rowCount()):
                writer.writerow([_cell_text(table, r, c) for c in range(table.columnCount())])
    except OSError as exc:
        QMessageBox.warning(parent, "Export Failed", f"Couldn't write the file:\n{exc}")
        return False
    QMessageBox.information(parent, "Export Complete", f"Exported {table.rowCount()} row(s) to:\n{path}")
    return True
