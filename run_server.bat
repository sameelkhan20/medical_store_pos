@echo off
echo Starting Medical Store POS System...
echo.
echo Activating Virtual Environment...
call ..\.venv\Scripts\activate
echo.
echo Server IP Address (Share this with PC 2):
ipconfig | findstr IPv4
echo.
echo Leave this black window open. Do not close it!
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause