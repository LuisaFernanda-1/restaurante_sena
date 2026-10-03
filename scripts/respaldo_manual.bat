@echo off
REM Doble clic para hacer un respaldo manual de la base de datos
"%~dp0..\backend\.venv\Scripts\python.exe" "%~dp0respaldo.py"
pause
