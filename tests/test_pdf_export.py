"""ui/pdf_export.py — the Sessions tab's "Export to PDF" companion to the
existing CSV export. Must produce a real, non-empty PDF file covering
every row (matching export_table_to_csv's contract), must escape cell
content so a villain name with an "&" or "<" in it can't break the
generated HTML, and must never touch disk if the save dialog is
cancelled.

NOTE: running these under QT_QPA_PLATFORM=offscreen (as CI does) prints a
"Windows fatal exception: code 0x80040155" during doc.print(printer) —
confirmed harmless: the test still passes, the resulting file is a valid
PDF, and the same test run against the real "windows" Qt platform (no
offscreen override) produces no such message at all. It's a first-chance
COM exception surfaced by Qt's PDF backend specifically under the
offscreen platform plugin, not an actual crash or real-usage risk."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))


def test_exports_a_real_nonempty_pdf_file(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QFileDialog
    from ui.pdf_export import export_table_to_pdf

    table = QTableWidget(2, 2)
    table.setHorizontalHeaderLabels(["Date", "Profit"])
    table.setItem(0, 0, QTableWidgetItem("2026-01-01"))
    table.setItem(0, 1, QTableWidgetItem("+$10.00"))
    table.setItem(1, 0, QTableWidgetItem("2026-01-02"))
    table.setItem(1, 1, QTableWidgetItem("-$5.00"))

    out = tmp_path / "summary.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))

    assert export_table_to_pdf(table, None, title="Test Report", subtitle="A subtitle") is True
    assert out.exists()
    assert out.stat().st_size > 0
    # A real PDF starts with this magic header regardless of content.
    assert out.read_bytes()[:5] == b"%PDF-"


def test_cancelling_the_save_dialog_writes_nothing(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QFileDialog
    from ui.pdf_export import export_table_to_pdf

    table = QTableWidget(1, 1)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    assert export_table_to_pdf(table, None, title="Test") is False
    assert list(tmp_path.iterdir()) == []


def test_html_special_characters_in_cells_are_escaped(qapp):
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from ui.pdf_export import _build_html

    table = QTableWidget(1, 1)
    table.setHorizontalHeaderLabels(["Name"])
    table.setItem(0, 0, QTableWidgetItem('<script>alert("x")</script> & Co'))

    html_out = _build_html(table, "Title", "Subtitle")
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "&amp; Co" in html_out


def test_title_and_subtitle_appear_in_the_generated_html(qapp):
    from PyQt6.QtWidgets import QTableWidget
    from ui.pdf_export import _build_html

    table = QTableWidget(0, 1)
    table.setHorizontalHeaderLabels(["A"])
    html_out = _build_html(table, "My Title", "My Subtitle")
    assert "My Title" in html_out
    assert "My Subtitle" in html_out
