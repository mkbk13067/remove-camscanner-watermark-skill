# Remove CamScanner Watermark Skill

A Codex skill for removing Scan/CamScanner overlay watermarks from scanned PDF files while preserving document content and native watermarks.

The bundled script removes only small independent PDF content-stream image blocks that match the CamScanner overlay pattern. It does not rasterize pages, inpaint images, or remove watermarks that are already embedded in the scanned page image.

## Desktop App

This repository also includes a Windows desktop app in `apps/camscanner-cleaner`.

The desktop app lets users drag in one or more PDF files, safely detects independent Scan/CamScanner overlay marks, and writes cleaned copies next to the original PDFs. It never overwrites source files.

Run from source:

```powershell
cd .\apps\camscanner-cleaner
python -m pip install -e .[dev]
python .\run_app.py
```

Build the Windows one-file executable:

```powershell
cd .\apps\camscanner-cleaner
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

The release executable is published on the GitHub Releases page as `扫描全能王水印清理器.exe`.

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

---

# 中文说明

这是一个用于 Codex 的 skill，可以从扫描型 PDF 中删除扫描全能王 / CamScanner 叠加水印，同时保留文档正文和文件自带水印。

内置脚本只会删除符合扫描全能王叠加水印特征的、小型、独立 PDF 内容流图片块。它不会把页面重新栅格化，不会做图像修复，也不会删除已经烘焙在扫描页面图片里的水印。

## 桌面软件

仓库也包含 Windows 桌面软件源码，位置在 `apps/camscanner-cleaner`。

桌面软件支持拖入一个或多个 PDF，先安全检测扫描全能王独立角标，再在原文件旁边生成去水印副本。它不会覆盖原文件。

从源码运行：

```powershell
cd .\apps\camscanner-cleaner
python -m pip install -e .[dev]
python .\run_app.py
```

打包 Windows 单文件程序：

```powershell
cd .\apps\camscanner-cleaner
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

发布版 `.exe` 会上传到 GitHub Releases 页面，文件名为 `扫描全能王水印清理器.exe`。

## 安全边界

请只在你有权修改的文档上使用本工具。

这个 skill 适合删除：

- Scan/CamScanner 叠加 logo
- 扫描全能王叠加水印
- 小型独立的 intsig 水印条、二维码或 logo 块

它必须保留：

- 大幅正文扫描页图片
- 印章、签名、条形码和公章
- 已经嵌入页面扫描图中的斜向水印或机构水印
- 不属于扫描全能王叠加层的可搜索 PDF 正文文本

## 安装

将 skill 文件夹复制到 Codex skills 目录：

```powershell
git clone https://github.com/mkbk13067/remove-camscanner-watermark-skill.git
Copy-Item -Recurse .\remove-camscanner-watermark-skill\skills\remove-camscanner-watermark "$env:USERPROFILE\.codex\skills\"
```

安装 Python 依赖：

```powershell
python -m pip install -r .\remove-camscanner-watermark-skill\requirements.txt
```

## 直接使用脚本

建议先 dry-run，只生成分析报告，不写出新 PDF：

```powershell
python .\skills\remove-camscanner-watermark\scripts\remove_camscanner_watermark.py "input.pdf" --dry-run --report "report.json"
```

确认报告没有异常后，再写出去水印副本：

```powershell
python .\skills\remove-camscanner-watermark\scripts\remove_camscanner_watermark.py "input.pdf" -o "output-clean.pdf" --report "output-report.json"
```

使用前请检查 JSON 报告。正常情况下，报告会列出被删除的小型叠加对象，并且 `warnings` 列表为空。

## 测试

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

如果本机有 Codex 的 skill creator 校验器，也可以验证 skill 结构：

```powershell
$env:PYTHONUTF8='1'
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" ".\skills\remove-camscanner-watermark"
```
