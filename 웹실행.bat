@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "WM_BOOTSTRAP=python"
where py >nul 2>nul
if not errorlevel 1 set "WM_BOOTSTRAP=py -3"
%WM_BOOTSTRAP% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 이상을 먼저 설치해 주세요. 설치할 때 Add Python to PATH를 선택하세요.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo 처음 실행을 준비하고 있습니다...
  %WM_BOOTSTRAP% -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import pymupdf,qrcode,PIL" >nul 2>nul
if errorlevel 1 (
  echo PDF 처리에 필요한 패키지를 설치합니다. 첫 실행에는 인터넷 연결이 필요합니다.
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" webapp.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo 실행하지 못했습니다. 위의 오류 내용을 확인해 주세요.
pause
exit /b 1
