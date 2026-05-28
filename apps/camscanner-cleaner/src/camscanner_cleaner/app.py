from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

import fitz
from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QColor,
    QIcon,
    QImage,
    QPainter,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import CleanReport, CleanStatus, clean_pdf


class JobStatus(str, Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    DONE = "done"
    NO_WATERMARK = "no_watermark"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


@dataclass
class PdfJob:
    path: Path
    status: JobStatus = JobStatus.WAITING
    message: str = "等待处理"
    output_path: Path | None = None
    report: CleanReport | None = None


@dataclass(frozen=True)
class WorkerResult:
    status: JobStatus
    message: str
    output_path: Path | None
    report: CleanReport | None


STATUS_TEXT = {
    JobStatus.WAITING: "等待中",
    JobStatus.PROCESSING: "处理中",
    JobStatus.DONE: "已完成",
    JobStatus.NO_WATERMARK: "未检测到可安全移除角标",
    JobStatus.NEEDS_REVIEW: "需人工检查",
    JobStatus.FAILED: "失败",
}


STATUS_COLOR = {
    JobStatus.WAITING: "#64748B",
    JobStatus.PROCESSING: "#2563EB",
    JobStatus.DONE: "#15803D",
    JobStatus.NO_WATERMARK: "#A16207",
    JobStatus.NEEDS_REVIEW: "#B45309",
    JobStatus.FAILED: "#B91C1C",
}


SVG_ICONS = {
    "folder-open": '<path d="M3 7.5V6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1.5"/><path d="M3.5 9.5h17L18.5 20h-13z"/>',
    "play": '<path d="M8 5v14l11-7z"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 15h10l1-15"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/>',
    "external-link": '<path d="M14 3h7v7"/><path d="M10 14L21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
}


def icon(name: str, color: str = "#334155") -> QIcon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" stroke="'
        + color
        + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        + SVG_ICONS[name]
        + "</svg>"
    )
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("DropZone")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(8)

        title = QLabel("拖入 PDF 文件")
        title.setObjectName("DropTitle")
        subtitle = QLabel("支持一次拖入多个 PDF；只会在原文件旁生成新文件，不覆盖原件。")
        subtitle.setObjectName("DropSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(_is_pdf_url(url) for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if _is_pdf_url(url)]
        self.files_dropped.emit(paths)
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)


class CleanerWorker(QThread):
    job_started = Signal(int)
    job_finished = Signal(int, object)
    progress_changed = Signal(int, int)

    def __init__(self, jobs: list[tuple[int, Path]]) -> None:
        super().__init__()
        self._jobs = jobs

    def run(self) -> None:
        total = len(self._jobs)
        for offset, (index, path) in enumerate(self._jobs, start=1):
            self.job_started.emit(index)
            try:
                report = clean_pdf(path)
                result = _result_from_report(report)
            except Exception as exc:
                result = WorkerResult(
                    status=JobStatus.FAILED,
                    message=f"{type(exc).__name__}: {exc}",
                    output_path=None,
                    report=None,
                )
            self.job_finished.emit(index, result)
            self.progress_changed.emit(offset, total)


class CleanerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[PdfJob] = []
        self.worker: CleanerWorker | None = None

        self.setWindowTitle("扫描全能王水印清理器")
        self.resize(1120, 720)
        self.setMinimumSize(980, 620)
        self.setWindowIcon(icon("file", "#2563EB"))

        self._build_ui()
        self._apply_style()
        self._update_actions()

    def add_pdf_paths(self, paths: Iterable[str | Path]) -> None:
        existing = {str(job.path.resolve()).casefold() for job in self.jobs}
        added = 0
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() != ".pdf" or not path.is_file():
                continue
            key = str(path.resolve()).casefold()
            if key in existing:
                continue
            existing.add(key)
            self.jobs.append(PdfJob(path=path))
            self._append_row(self.jobs[-1])
            added += 1

        if added:
            self.table.selectRow(len(self.jobs) - 1)
        self._update_actions()
        self._update_summary()

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择 PDF 文件",
            str(Path.home()),
            "PDF 文件 (*.pdf)",
        )
        self.add_pdf_paths(files)

    def start_processing(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        pending = [
            (index, job.path)
            for index, job in enumerate(self.jobs)
            if job.status == JobStatus.WAITING
        ]
        if not pending:
            QMessageBox.information(self, "没有待处理文件", "当前队列中没有等待处理的 PDF。")
            return

        self.worker = CleanerWorker(pending)
        self.worker.job_started.connect(self._mark_processing)
        self.worker.job_finished.connect(self._mark_finished)
        self.worker.progress_changed.connect(self._update_progress)
        self.worker.finished.connect(self._processing_finished)
        self.start_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.summary_label.setText("正在处理队列...")
        self.worker.start()

    def clear_finished(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.jobs = [job for job in self.jobs if job.status == JobStatus.WAITING]
        self._reload_table()
        self._update_actions()
        self._update_summary()

    def open_selected_output(self) -> None:
        job = self._selected_job()
        if job and job.output_path and job.output_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.output_path)))

    def open_selected_folder(self) -> None:
        job = self._selected_job()
        target = job.output_path if job and job.output_path else job.path if job else None
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(_is_pdf_url(url) for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        self.add_pdf_paths(Path(url.toLocalFile()) for url in event.mimeData().urls())

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("扫描全能王水印清理器")
        title.setObjectName("AppTitle")
        subtitle = QLabel("安全移除独立角标。不会擦除正文、印章或文档自身斜向水印。")
        subtitle.setObjectName("AppSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch(1)

        self.choose_button = QPushButton("选择 PDF")
        self.choose_button.setIcon(icon("folder-open"))
        self.choose_button.clicked.connect(self.choose_files)
        self.start_button = QPushButton("开始处理")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setIcon(icon("play", "#FFFFFF"))
        self.start_button.clicked.connect(self.start_processing)
        self.clear_button = QPushButton("清理已完成")
        self.clear_button.setIcon(icon("trash"))
        self.clear_button.clicked.connect(self.clear_finished)
        header.addWidget(self.choose_button)
        header.addWidget(self.start_button)
        header.addWidget(self.clear_button)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 12, 0)
        left_layout.setSpacing(14)
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self.add_pdf_paths)
        left_layout.addWidget(self.drop_zone)

        self.summary_label = QLabel("队列为空")
        self.summary_label.setObjectName("SummaryLabel")
        left_layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文件", "状态", "结果"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_detail)
        left_layout.addWidget(self.table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(12)

        detail_title = QLabel("文件详情")
        detail_title.setObjectName("PanelTitle")
        self.detail_label = QLabel("选择队列中的文件查看检测结果。")
        self.detail_label.setObjectName("DetailLabel")
        self.detail_label.setWordWrap(True)
        self.preview_label = QLabel("预览会显示首个命中页")
        self.preview_label.setObjectName("PreviewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(360)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        action_row = QHBoxLayout()
        self.open_file_button = QPushButton("打开文件")
        self.open_file_button.setIcon(icon("external-link"))
        self.open_file_button.clicked.connect(self.open_selected_output)
        self.open_folder_button = QPushButton("打开文件夹")
        self.open_folder_button.setIcon(icon("folder-open"))
        self.open_folder_button.clicked.connect(self.open_selected_folder)
        action_row.addWidget(self.open_file_button)
        action_row.addWidget(self.open_folder_button)

        right_layout.addWidget(detail_title)
        right_layout.addWidget(self.detail_label)
        right_layout.addWidget(self.preview_label, 1)
        right_layout.addLayout(action_row)
        splitter.addWidget(right)
        splitter.setSizes([720, 360])
        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #F6F8FB;
                color: #0F172A;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            #AppTitle {
                font-size: 24px;
                font-weight: 700;
                color: #0B1220;
            }
            #AppSubtitle, #DropSubtitle, #SummaryLabel, #DetailLabel {
                color: #64748B;
            }
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #D8DEE8;
                border-radius: 7px;
                padding: 9px 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #F8FAFC;
                border-color: #B9C4D3;
            }
            QPushButton:disabled {
                color: #A8B1C0;
                background: #EFF3F8;
            }
            #PrimaryButton {
                background: #1D4ED8;
                color: white;
                border-color: #1D4ED8;
            }
            #PrimaryButton:hover {
                background: #1E40AF;
            }
            #DropZone {
                background: #FFFFFF;
                border: 1px dashed #AEB9C9;
                border-radius: 8px;
            }
            #DropZone[dragging="true"] {
                background: #EEF5FF;
                border-color: #2563EB;
            }
            #DropTitle {
                color: #0F172A;
                font-size: 18px;
                font-weight: 700;
            }
            QTableWidget {
                background: #FFFFFF;
                border: 1px solid #E0E6EF;
                border-radius: 8px;
                gridline-color: #EEF2F7;
                selection-background-color: #EAF2FF;
                selection-color: #0F172A;
            }
            QHeaderView::section {
                background: #F8FAFC;
                border: none;
                border-bottom: 1px solid #E0E6EF;
                color: #475569;
                font-weight: 700;
                padding: 9px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #F1F5F9;
            }
            #PanelTitle {
                color: #0F172A;
                font-size: 16px;
                font-weight: 700;
            }
            #PreviewLabel {
                background: #FFFFFF;
                border: 1px solid #E0E6EF;
                border-radius: 8px;
                color: #94A3B8;
            }
            """
        )

    def _append_row(self, job: PdfJob) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._write_row(row, job)

    def _reload_table(self) -> None:
        self.table.setRowCount(0)
        for job in self.jobs:
            self._append_row(job)

    def _write_row(self, row: int, job: PdfJob) -> None:
        file_item = QTableWidgetItem(job.path.name)
        file_item.setToolTip(str(job.path))
        status_item = QTableWidgetItem(STATUS_TEXT[job.status])
        status_item.setForeground(QColor(STATUS_COLOR[job.status]))
        result_item = QTableWidgetItem(job.message)
        result_item.setToolTip(job.message)
        self.table.setItem(row, 0, file_item)
        self.table.setItem(row, 1, status_item)
        self.table.setItem(row, 2, result_item)

    def _mark_processing(self, index: int) -> None:
        job = self.jobs[index]
        job.status = JobStatus.PROCESSING
        job.message = "正在检测并清理..."
        self._write_row(index, job)
        self.table.selectRow(index)
        self._update_detail()

    def _mark_finished(self, index: int, result: WorkerResult) -> None:
        job = self.jobs[index]
        job.status = result.status
        job.message = result.message
        job.output_path = result.output_path
        job.report = result.report
        self._write_row(index, job)
        self.table.selectRow(index)
        self._update_detail()

    def _update_progress(self, done: int, total: int) -> None:
        self.summary_label.setText(f"正在处理 {done}/{total}")

    def _processing_finished(self) -> None:
        self.worker = None
        self._update_actions()
        self._update_summary()

    def _update_actions(self) -> None:
        is_running = self.worker is not None and self.worker.isRunning()
        has_waiting = any(job.status == JobStatus.WAITING for job in self.jobs)
        self.start_button.setEnabled(has_waiting and not is_running)
        self.clear_button.setEnabled(bool(self.jobs) and not is_running)
        selected = self._selected_job()
        can_open_file = bool(selected and selected.output_path and selected.output_path.exists())
        self.open_file_button.setEnabled(can_open_file)
        self.open_folder_button.setEnabled(selected is not None)

    def _update_summary(self) -> None:
        if not self.jobs:
            self.summary_label.setText("队列为空")
            return
        done = sum(1 for job in self.jobs if job.status == JobStatus.DONE)
        waiting = sum(1 for job in self.jobs if job.status == JobStatus.WAITING)
        review = sum(1 for job in self.jobs if job.status == JobStatus.NEEDS_REVIEW)
        failed = sum(1 for job in self.jobs if job.status == JobStatus.FAILED)
        self.summary_label.setText(
            f"共 {len(self.jobs)} 个 PDF，已完成 {done}，等待 {waiting}，需检查 {review}，失败 {failed}"
        )

    def _selected_job(self) -> PdfJob | None:
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not indexes:
            return None
        row = indexes[0].row()
        if row < 0 or row >= len(self.jobs):
            return None
        return self.jobs[row]

    def _update_detail(self) -> None:
        job = self._selected_job()
        if job is None:
            self.detail_label.setText("选择队列中的文件查看检测结果。")
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("预览会显示首个命中页")
            self._update_actions()
            return

        lines = [
            f"文件：{job.path.name}",
            f"状态：{STATUS_TEXT[job.status]}",
            f"位置：{job.path}",
        ]
        if job.report:
            lines.append(f"页数：{job.report.pages}")
            lines.append(f"命中页：{', '.join(map(str, job.report.hit_pages)) or '无'}")
            lines.append(f"移除角标：{job.report.removed_count}")
            if job.report.warnings:
                lines.append("警告：" + "；".join(warning.error for warning in job.report.warnings[:2]))
        if job.output_path:
            lines.append(f"输出：{job.output_path}")
        self.detail_label.setText("\n".join(lines))
        self._render_preview(job)
        self._update_actions()

    def _render_preview(self, job: PdfJob) -> None:
        source = job.output_path if job.output_path and job.output_path.exists() else job.path
        page_number = 1
        if job.report and job.report.hit_pages:
            page_number = job.report.hit_pages[0]
        try:
            pixmap = render_page(source, page_number)
        except Exception:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("无法生成预览")
            return
        self.preview_label.setText("")
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


def render_page(path: Path, page_number: int) -> QPixmap:
    with fitz.open(path) as document:
        page = document.load_page(max(0, min(page_number - 1, document.page_count - 1)))
        pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        image = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888,
        ).copy()
    return QPixmap.fromImage(image)


def _is_pdf_url(url: QUrl) -> bool:
    return url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".pdf"


def _result_from_report(report: CleanReport) -> WorkerResult:
    if report.status == CleanStatus.CLEANED:
        output = Path(report.output) if report.output else None
        return WorkerResult(
            status=JobStatus.DONE,
            message=f"已生成：{output.name if output else ''}",
            output_path=output,
            report=report,
        )
    if report.status == CleanStatus.NO_WATERMARK:
        return WorkerResult(
            status=JobStatus.NO_WATERMARK,
            message="未检测到可安全移除的独立角标",
            output_path=None,
            report=report,
        )
    if report.status == CleanStatus.NEEDS_REVIEW:
        message = "；".join(warning.error for warning in report.warnings[:2])
        return WorkerResult(
            status=JobStatus.NEEDS_REVIEW,
            message=message or "检测结果需要人工检查",
            output_path=Path(report.output) if report.output else None,
            report=report,
        )
    return WorkerResult(
        status=JobStatus.FAILED,
        message="处理失败",
        output_path=None,
        report=report,
    )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("扫描全能王水印清理器")
    window = CleanerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
