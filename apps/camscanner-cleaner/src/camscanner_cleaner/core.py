from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject


class CleanStatus(str, Enum):
    READY = "ready"
    CLEANED = "cleaned"
    NO_WATERMARK = "no_watermark"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SourceImage:
    width: int
    height: int


@dataclass(frozen=True)
class ImageBlock:
    object_name: str
    box: Box
    source_image: SourceImage


@dataclass(frozen=True)
class PageRemoval:
    page: int
    objects: list[str]
    blocks: list[ImageBlock]


@dataclass(frozen=True)
class CleanWarning:
    page: int | None
    error: str


@dataclass(frozen=True)
class CleanReport:
    input: str
    output: str | None
    dry_run: bool
    producer: str
    pages: int
    removed: list[PageRemoval]
    warnings: list[CleanWarning]
    status: CleanStatus

    @property
    def removed_count(self) -> int:
        return sum(len(page.blocks) for page in self.removed)

    @property
    def hit_pages(self) -> list[int]:
        return [page.page for page in self.removed]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["removed_count"] = self.removed_count
        data["hit_pages"] = self.hit_pages
        return data


def make_output_path(input_path: str | Path) -> Path:
    source = Path(input_path)
    base = source.with_name(f"{source.stem}-去扫描全能王水印{source.suffix}")
    if not base.exists():
        return base

    counter = 2
    while True:
        candidate = source.with_name(
            f"{source.stem}-去扫描全能王水印 ({counter}){source.suffix}"
        )
        if not candidate.exists():
            return candidate
        counter += 1


def analyze_pdf(input_path: str | Path) -> CleanReport:
    return _process_pdf(Path(input_path), output_path=None, dry_run=True)


def clean_pdf(input_path: str | Path, output_path: str | Path | None = None) -> CleanReport:
    source = Path(input_path)
    destination = Path(output_path) if output_path is not None else make_output_path(source)

    analysis = analyze_pdf(source)
    if analysis.status != CleanStatus.READY:
        return analysis

    clean_report = _process_pdf(source, output_path=destination, dry_run=False)
    if clean_report.warnings:
        return CleanReport(
            **{
                **clean_report.__dict__,
                "status": CleanStatus.NEEDS_REVIEW,
            }
        )

    post_report = analyze_pdf(destination)
    if post_report.warnings or post_report.removed_count:
        warnings = list(clean_report.warnings) + list(post_report.warnings)
        if post_report.removed_count:
            warnings.append(
                CleanWarning(
                    page=None,
                    error="清理后仍检测到疑似扫描全能王角标，输出文件需人工检查。",
                )
            )
        return CleanReport(
            **{
                **clean_report.__dict__,
                "warnings": warnings,
                "status": CleanStatus.NEEDS_REVIEW,
            }
        )

    return CleanReport(
        **{
            **clean_report.__dict__,
            "status": CleanStatus.CLEANED,
        }
    )


def _as_float(value: Any) -> float:
    return float(value)


def _image_sizes(page: Any) -> dict[str, SourceImage]:
    resources = page.get("/Resources") or {}
    if hasattr(resources, "get_object"):
        resources = resources.get_object()
    xobjects = resources.get("/XObject") or {}
    if hasattr(xobjects, "get_object"):
        xobjects = xobjects.get_object()

    images: dict[str, SourceImage] = {}
    for name, ref in xobjects.items():
        obj = ref.get_object() if hasattr(ref, "get_object") else ref
        if obj.get("/Subtype") == "/Image":
            images[str(name)] = SourceImage(
                width=int(obj.get("/Width", 0)),
                height=int(obj.get("/Height", 0)),
            )
    return images


def _block_box(block_operations: list[tuple[Any, bytes]]) -> Box | None:
    translate_x = 0.0
    translate_y = 0.0
    width = None
    height = None

    for operands, operator in block_operations:
        if operator != b"cm" or len(operands) != 6:
            continue

        a, b, c, d, e, f = [_as_float(value) for value in operands]
        has_no_skew = abs(b) < 0.001 and abs(c) < 0.001
        is_translation = abs(a - 1.0) < 0.001 and abs(d - 1.0) < 0.001
        if has_no_skew and is_translation:
            translate_x += e
            translate_y += f
        elif has_no_skew:
            width = abs(a)
            height = abs(d)
            translate_x += e
            translate_y += f

    if width is None or height is None:
        return None
    return Box(x=translate_x, y=translate_y, width=width, height=height)


def _is_watermark_candidate(
    name: str,
    box: Box | None,
    images: dict[str, SourceImage],
    page_width: float,
    page_height: float,
) -> bool:
    if box is None or name not in images:
        return False

    image = images[name]
    page_area = page_width * page_height
    image_area = box.width * box.height

    is_small_on_page = (
        box.width <= page_width * 0.26
        and box.height <= page_height * 0.09
        and image_area <= page_area * 0.02
    )
    is_small_source_image = image.width <= 600 and image.height <= 250
    in_margin = (
        box.x <= page_width * 0.08
        or box.x + box.width >= page_width * 0.92
        or box.y <= page_height * 0.08
        or box.y + box.height >= page_height * 0.92
    )

    return is_small_on_page and is_small_source_image and in_margin


def _find_watermark_blocks(
    operations: list[tuple[Any, bytes]],
    images: dict[str, SourceImage],
    page_width: float,
    page_height: float,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    stack: list[int] = []

    for index, (_operands, operator) in enumerate(operations):
        if operator == b"q":
            stack.append(index)
        elif operator == b"Q" and stack:
            start = stack.pop()
            end = index
            block = operations[start : end + 1]
            do_ops = [
                (operands, op)
                for operands, op in block
                if op == b"Do" and len(operands) == 1
            ]
            if len(do_ops) != 1:
                continue

            name = str(do_ops[0][0][0])
            box = _block_box(block)
            if _is_watermark_candidate(name, box, images, page_width, page_height):
                blocks.append(
                    {
                        "start": start,
                        "end": end,
                        "block": ImageBlock(
                            object_name=name,
                            box=box,
                            source_image=images[name],
                        ),
                    }
                )

    return sorted(blocks, key=lambda item: item["start"], reverse=True)


def _status_for(removed: list[PageRemoval], warnings: list[CleanWarning]) -> CleanStatus:
    if warnings:
        return CleanStatus.NEEDS_REVIEW
    if removed:
        return CleanStatus.READY
    return CleanStatus.NO_WATERMARK


def _process_pdf(
    input_path: Path,
    output_path: Path | None = None,
    dry_run: bool = False,
) -> CleanReport:
    removed: list[PageRemoval] = []
    warnings: list[CleanWarning] = []
    pages = 0
    producer = ""

    try:
        reader = PdfReader(str(input_path))
        pages = len(reader.pages)
        producer = str(reader.metadata.get("/Producer", "")) if reader.metadata else ""
    except Exception as exc:
        return CleanReport(
            input=str(input_path),
            output=str(output_path) if output_path else None,
            dry_run=dry_run,
            producer="",
            pages=0,
            removed=[],
            warnings=[CleanWarning(page=None, error=f"{type(exc).__name__}: {exc}")],
            status=CleanStatus.NEEDS_REVIEW,
        )

    writer = PdfWriter() if not dry_run else None

    for page_index, page in enumerate(reader.pages, start=1):
        try:
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            images = _image_sizes(page)
            contents = page.get_contents()
            if contents is None:
                blocks: list[dict[str, Any]] = []
                content = None
            else:
                content = ContentStream(contents, reader)
                blocks = _find_watermark_blocks(
                    content.operations,
                    images,
                    page_width=page_width,
                    page_height=page_height,
                )

            if blocks:
                block_models = [block["block"] for block in reversed(blocks)]
                removed.append(
                    PageRemoval(
                        page=page_index,
                        objects=[block.object_name for block in block_models],
                        blocks=block_models,
                    )
                )

            if not dry_run and writer is not None:
                if blocks and content is not None:
                    for block in blocks:
                        del content.operations[block["start"] : block["end"] + 1]
                    page[NameObject("/Contents")] = content
                writer.add_page(page)

        except Exception as exc:
            warnings.append(
                CleanWarning(page=page_index, error=f"{type(exc).__name__}: {exc}")
            )
            if not dry_run and writer is not None:
                writer.add_page(page)

    if not dry_run and writer is not None and output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            writer.write(handle)

    return CleanReport(
        input=str(input_path),
        output=str(output_path) if output_path else None,
        dry_run=dry_run,
        producer=producer,
        pages=pages,
        removed=removed,
        warnings=warnings,
        status=_status_for(removed, warnings),
    )
