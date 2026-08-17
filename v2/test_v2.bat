@echo off
cd /d "%~dp0"
echo === determinism ===
python -m pb2.harness.golden determinism
echo === goldens ===
python -m pb2.harness.golden verify
echo === scale ===
python -m pb2.harness.bench
