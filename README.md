# Remove CamScanner Watermark Skill

A Codex skill for removing Scan/CamScanner overlay watermarks from scanned PDF files while preserving document content and native watermarks.

The bundled script removes only small independent PDF content-stream image blocks that match the CamScanner overlay pattern. It does not rasterize pages, inpaint images, or remove watermarks that are already embedded in the scanned page image.

## Safety Boundary

Use this only on documents you have the right to modify.

This skill is designed to remove:

- Scan/CamScanner overlay logos
- 扫描全能王 overlay marks
- Small independent intsig watermark strips or QR/logo blocks

It must preserve:

- The large scanned page image
- Stamps, signatures, barcodes, and seals
- Native diagonal or institutional watermarks embedded in the page scan
- Searchable PDF text that is not part of the CamScanner overlay

## Install

Copy the skill folder into your Codex skills directory:

```powershell
git clone https://github.com/mkbk13067/remove-camscanner-watermark-skill.git
Copy-Item -Recurse .\remove-camscanner-watermark-skill\skills\remove-camscanner-watermark "$env:USERPROFILE\.codex\skills\"
```

Install the Python dependency:

```powershell
python -m pip install -r .\remove-camscanner-watermark-skill\requirements.txt
```

## Use The Script Directly

Dry-run first:

```powershell
python .\skills\remove-camscanner-watermark\scripts\remove_camscanner_watermark.py "input.pdf" --dry-run --report "report.json"
```

Write a cleaned copy:

```powershell
python .\skills\remove-camscanner-watermark\scripts\remove_camscanner_watermark.py "input.pdf" -o "output-clean.pdf" --report "output-report.json"
```

Review the JSON report before trusting the result. A normal report lists the removed small overlay objects and has an empty `warnings` list.

## Test

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

Validate the skill with Codex's skill creator validator if available:

```powershell
$env:PYTHONUTF8='1'
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" ".\skills\remove-camscanner-watermark"
```
