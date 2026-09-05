"""ui/csv_export.py — must handle both plain QTableWidgetItem cells and
widget-based cells (the hand-list dialog's card badges are QLabels inside
a container, not item text) the same way, and must never silently corrupt
data containing commas/quotes (a player name genuinely can contain either)."""
import csv

import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch):
    # export_table_to_csv shows a confirmation/error QMessageBox itself —
    # a real one would block the test forever waiting for a click.
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))


def test_exports_plain_item_cells(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QFileDialog
    from ui.csv_export import export_table_to_csv

    table = QTableWidget(2, 2)
    table.setHorizontalHeaderLabels(["Name", "Hands"])
    table.setItem(0, 0, QTableWidgetItem("Alice"))
    table.setItem(0, 1, QTableWidgetItem("100"))
    table.setItem(1, 0, QTableWidgetItem("Bob"))
    table.setItem(1, 1, QTableWidgetItem("200"))

    out = tmp_path / "export.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))

    assert export_table_to_csv(table, None) is True
    rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
    assert rows == [["Name", "Hands"], ["Alice", "100"], ["Bob", "200"]]


def test_exports_widget_based_cells(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QWidget, QHBoxLayout, QLabel, QFileDialog
    from ui.csv_export import export_table_to_csv

    table = QTableWidget(1, 1)
    table.setHorizontalHeaderLabels(["Hole Cards"])
    cell = QWidget()
    lay = QHBoxLayout(cell)
    lay.addWidget(QLabel("A♠"))
    lay.addWidget(QLabel("K♥"))
    table.setCellWidget(0, 0, cell)

    out = tmp_path / "cards.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))

    export_table_to_csv(table, None)
    rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
    assert rows == [["Hole Cards"], ["A♠ K♥"]]


def test_values_with_commas_and_quotes_survive_a_round_trip(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QFileDialog
    from ui.csv_export import export_table_to_csv

    table = QTableWidget(1, 1)
    table.setHorizontalHeaderLabels(["Name"])
    tricky = 'Smith, "The Shark"'
    table.setItem(0, 0, QTableWidgetItem(tricky))

    out = tmp_path / "tricky.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))

    export_table_to_csv(table, None)
    rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
    assert rows == [["Name"], [tricky]]


def test_cancelling_the_save_dialog_writes_nothing(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QFileDialog
    from ui.csv_export import export_table_to_csv

    table = QTableWidget(1, 1)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    assert export_table_to_csv(table, None) is False
    assert list(tmp_path.iterdir()) == []


def test_empty_table_exports_header_only(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QFileDialog
    from ui.csv_export import export_table_to_csv

    table = QTableWidget(0, 2)
    table.setHorizontalHeaderLabels(["A", "B"])
    out = tmp_path / "empty.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))

    export_table_to_csv(table, None)
    rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
    assert rows == [["A", "B"]]
