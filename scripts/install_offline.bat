@echo off
set PYTHON_EXE=python
if not "%~1"=="" set PYTHON_EXE=%~1
%PYTHON_EXE% -m pip install --no-index --find-links vendor\wheels -r requirements.lock.txt
