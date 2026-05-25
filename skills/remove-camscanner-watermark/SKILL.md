---
name: remove-camscanner-watermark
description: Use when removing Scan/CamScanner, 扫描全能王, CS 扫描全能王, or intsig overlay watermarks from scanned PDF files while preserving document content, stamps, signatures, native diagonal watermarks, and embedded page-image marks.
---

# Remove CamScanner Watermark

## Core Rule

Remove only CamScanner overlay objects that are separate PDF content-stream elements. Do not rasterize pages, inpaint images, erase diagonal/native watermarks, or alter the large scanned page image unless the user explicitly asks for image restoration after being warned about quality and content risk.

## Workflow

1. Identify target PDFs and keep originals unchanged.
2. Run the bundled script in dry-run mode first:

   ```powershell
   python "<skill>/scripts/remove_camscanner_watermark.py" "input.pdf" --dry-run --report "report.json"
   ```

3. Proceed only when the report shows small independent watermark image blocks and no parse warnings.
4. Write cleaned copies to a separate output directory:

   ```powershell
   python "<skill>/scripts/remove_camscanner_watermark.py" "input.pdf" -o "output/input-去扫描全能王水印.pdf" --report "output/input-report.json"
   ```

5. Verify structurally that the small overlay object was removed and the large page image remains.
6. Render-check representative pages with `pdftoppm` when available.

## Safety Checks

Use the script's default detector. It only removes a block when all conditions match:

- The page content has an independent `q ... Q` graphics-state block.
- The block contains exactly one image draw operation (`Do`).
- The drawn image is small relative to the page.
- The source image is small, consistent with a logo/QR/watermark strip.
- The block is near a page margin or corner.

If a visible watermark remains after this removal, treat it as embedded in the scanned page image unless a fresh content-stream inspection proves otherwise. Native marks such as funder, archive, institution, approval, or diagonal document watermarks must be preserved.

## Verification

Confirm before reporting success:

- Page count matches the original.
- Removed objects are listed in the JSON report.
- Each checked cleaned page still has its large page image draw operation.
- No warnings appear in the report.
- Rendered samples are legible and still show document-native marks that were part of the scan.

For quick structural inspection, the script report is usually enough. For high-stakes files, render first, last, and any visually unusual pages.

## Common Mistakes

- Do not delete every `/X1`; object names are PDF-local and not reliable by themselves.
- Do not delete all `Tj` text operations; that can remove real text in searchable PDFs.
- Do not remove or blur diagonal watermarks that are baked into the page scan.
- Do not overwrite the original PDF.
