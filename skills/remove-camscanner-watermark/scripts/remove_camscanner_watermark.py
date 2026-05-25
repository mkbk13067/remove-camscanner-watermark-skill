import argparse
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject


def _as_float(value):
    return float(value)


def _image_sizes(page):
    resources = page.get("/Resources") or {}
    xobjects = resources.get("/XObject") or {}
    if hasattr(xobjects, "get_object"):
        xobjects = xobjects.get_object()

    images = {}
    for name, ref in xobjects.items():
        obj = ref.get_object()
        if obj.get("/Subtype") == "/Image":
            images[str(name)] = {
                "width": int(obj.get("/Width", 0)),
                "height": int(obj.get("/Height", 0)),
            }
    return images


def _block_box(block_operations):
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
    return {
        "x": translate_x,
        "y": translate_y,
        "width": width,
        "height": height,
    }


def _is_watermark_candidate(name, box, images, page_width, page_height):
    if box is None or name not in images:
        return False

    image = images[name]
    page_area = page_width * page_height
    image_area = box["width"] * box["height"]

    is_small_on_page = (
        box["width"] <= page_width * 0.26
        and box["height"] <= page_height * 0.09
        and image_area <= page_area * 0.02
    )
    is_small_source_image = image["width"] <= 600 and image["height"] <= 250
    in_margin = (
        box["x"] <= page_width * 0.08
        or box["x"] + box["width"] >= page_width * 0.92
        or box["y"] <= page_height * 0.08
        or box["y"] + box["height"] >= page_height * 0.92
    )

    return is_small_on_page and is_small_source_image and in_margin


def find_watermark_blocks(operations, images, page_width, page_height):
    blocks = []
    stack = []

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
                        "object": name,
                        "box": box,
                        "source_image": images.get(name),
                    }
                )

    return sorted(blocks, key=lambda item: item["start"], reverse=True)


def process_pdf(input_path, output_path=None, dry_run=False):
    reader = PdfReader(str(input_path))
    writer = PdfWriter() if not dry_run else None
    report = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "dry_run": dry_run,
        "producer": str(reader.metadata.get("/Producer", "")) if reader.metadata else "",
        "pages": len(reader.pages),
        "removed": [],
        "warnings": [],
    }

    for page_index, page in enumerate(reader.pages, start=1):
        try:
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            images = _image_sizes(page)
            content = ContentStream(page.get_contents(), reader)
            blocks = find_watermark_blocks(
                content.operations,
                images,
                page_width=page_width,
                page_height=page_height,
            )

            if blocks:
                report["removed"].append(
                    {
                        "page": page_index,
                        "objects": [block["object"] for block in blocks],
                        "blocks": [
                            {
                                "object": block["object"],
                                "box": block["box"],
                                "source_image": block["source_image"],
                            }
                            for block in blocks
                        ],
                    }
                )

            if not dry_run:
                for block in blocks:
                    del content.operations[block["start"] : block["end"] + 1]
                if blocks:
                    page[NameObject("/Contents")] = content
                writer.add_page(page)

        except Exception as exc:
            report["warnings"].append(
                {"page": page_index, "error": f"{type(exc).__name__}: {exc}"}
            )
            if not dry_run:
                writer.add_page(page)

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as handle:
            writer.write(handle)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Remove likely Scan/CamScanner overlay image blocks from scanned PDFs."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if not args.dry_run and args.output is None:
        parser.error("--output is required unless --dry-run is used")

    report = process_pdf(args.input, args.output, args.dry_run)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
