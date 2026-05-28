import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from camscanner_cleaner.app import CleanerWindow, JobStatus


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_add_pdf_paths_filters_duplicates_and_enables_processing(tmp_path: Path) -> None:
    _app()
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    ignored = tmp_path / "notes.txt"
    first.write_bytes(b"%PDF-1.4\n")
    second.write_bytes(b"%PDF-1.4\n")
    ignored.write_text("not pdf", encoding="utf-8")

    window = CleanerWindow()
    window.add_pdf_paths([first, ignored, first, second])

    assert len(window.jobs) == 2
    assert [job.path for job in window.jobs] == [first, second]
    assert all(job.status == JobStatus.WAITING for job in window.jobs)
    assert window.start_button.isEnabled()
    assert window.table.rowCount() == 2
