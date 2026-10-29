@echo off
cd /d "%~dp0"
if not exist .venv (
  uv venv --python 3.12 .venv && uv pip install -e . && .venv\Scripts\python.exe -m playwright install chromium
)
.venv\Scripts\python.exe -m jobhunt.cli serve %*
