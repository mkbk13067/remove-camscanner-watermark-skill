# 扫描全能王水印清理器 Desktop App

Windows desktop app for safely removing independent Scan/CamScanner overlay marks from PDF files.

## Features

- Drag in one or more PDF files.
- Analyze each file before cleaning.
- Generate `原名-去扫描全能王水印.pdf` next to the original file.
- Never overwrite the original PDF.
- Preserve document text, seals, signatures, large scanned page images, and native diagonal watermarks.
- Mark ambiguous or malformed PDFs as needing manual review instead of forcing edits.

## Run From Source

```powershell
python -m pip install -e .[dev]
python run_app.py
```

## Test

```powershell
python -m pytest -q
```

## Build Windows Release

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

The build writes:

- `dist\扫描全能王水印清理器.exe`
- `dist\README.txt`

The executable is unsigned, so Windows may show an unknown-publisher warning.
