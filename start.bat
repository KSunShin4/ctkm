@echo off
setlocal
cd /d "%~dp0"

echo.
echo === Khoi dong CTKM Pipeline ===

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [!] Da tao .env tu .env.example - hay dien GEMINI_API_KEY truoc khi chay pipeline!
)

if not exist "frontend\node_modules" (
  echo [X] Chua cai frontend. Chay: start.bat --setup
  exit /b 1
)

where python >nul 2>&1
if %errorlevel% neq 0 (
  echo [X] Python chua duoc cai.
  exit /b 1
)

python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
  echo [X] Chua cai Python deps. Chay: start.bat --setup
  exit /b 1
)

if /i "%~1"=="--setup" (
  echo.
  echo === Cai dat CTKM Pipeline ===
  echo.
  pip install -r backend\requirements_backend.txt
  cd frontend
  call npm install
  cd ..
  echo [OK] Setup hoan tat! Chay: start.bat
  exit /b 0
)

echo [OK] Backend  - http://localhost:8000
echo [OK] Frontend - http://localhost:5173
echo [OK] API docs - http://localhost:8000/docs
echo.

start "CTKM Backend" cmd /k "cd /d %~dp0 && python -m uvicorn backend.main_api:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul
start "CTKM Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Da mo 2 cua so terminal (Backend + Frontend).
echo Mo trinh duyet: http://localhost:5173
echo.
