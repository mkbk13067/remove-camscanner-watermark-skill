from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from camscanner_cleaner.core import (
    CleanStatus,
    analyze_pdf,
    clean_pdf,
    make_output_path,
)


def _image_object(width: int, height: int) -> DecodedStreamObject:
    image = DecodedStreamObject()
    image.set_data(bytes([255]) * width * height)
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(width),
            NameObject("/Height"): NumberObject(height),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    return image


def make_pdf(path: Path, *, include_margin_mark: bool, include_center_mark: bool = False) -> Path:
    writer = PdfWriter()
    page = writer.add_blank_page(width=580, height=820)
    page_image = writer._add_object(_image_object(1200, 1600))
    mark_image = writer._add_object(_image_object(312, 90))

    xobjects = DictionaryObject(
        {
            NameObject("/ImPage"): page_image,
            NameObject("/ImMark"): mark_image,
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): xobjects}
    )

    operations = [
        "q",
        "560 0 0 800 10 10 cm",
        "/ImPage Do",
        "Q",
    ]
    if include_margin_mark:
        operations.extend(
            [
                "q",
                "104 0 0 30 476 10 cm",
                "/ImMark Do",
                "Q",
            ]
        )
    if include_center_mark:
        operations.extend(
            [
                "q",
                "104 0 0 30 238 390 cm",
                "/ImMark Do",
                "Q",
            ]
        )

    stream = DecodedStreamObject()
    stream.set_data(("\n".join(operations) + "\n").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)

    with path.open("wb") as handle:
        writer.write(handle)
    return path


def test_analyze_pdf_detects_safe_margin_overlay(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "input.pdf", include_margin_mark=True)

    report = analyze_pdf(pdf)

    assert report.status == CleanStatus.READY
    assert report.pages == 1
    assert report.removed_count == 1
    assert report.hit_pages == [1]
    assert report.warnings == []
    assert report.removed[0].blocks[0].object_name == "/ImMark"


def test_clean_pdf_removes_margin_overlay_and_preserves_page_count(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "input.pdf", include_margin_mark=True)
    output = tmp_path / "cleaned.pdf"

    report = clean_pdf(pdf, output)

    assert report.status == CleanStatus.CLEANED
    assert output.exists()
    assert len(PdfReader(str(output)).pages) == len(PdfReader(str(pdf)).pages)
    assert analyze_pdf(output).status == CleanStatus.NO_WATERMARK
    assert analyze_pdf(output).removed_count == 0


def test_center_small_image_is_not_removed(tmp_path: Path) -> None:
    pdf = make_pdf(
        tmp_path / "center.pdf",
        include_margin_mark=False,
        include_center_mark=True,
    )

    report = analyze_pdf(pdf)

    assert report.status == CleanStatus.NO_WATERMARK
    assert report.removed_count == 0


def test_make_output_path_never_overwrites_existing_file(tmp_path: Path) -> None:
    pdf = tmp_path / "报告.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    first = tmp_path / "报告-去扫描全能王水印.pdf"
    first.write_bytes(b"existing")

    output = make_output_path(pdf)

    assert output == tmp_path / "报告-去扫描全能王水印 (2).pdf"


def test_analyze_pdf_reports_invalid_pdf_as_warning(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_text("not a pdf", encoding="utf-8")

    report = analyze_pdf(pdf)

    assert report.status == CleanStatus.NEEDS_REVIEW
    assert report.warnings
    assert report.warnings[0].error
