@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

if not exist ".env" copy ".env.example" ".env" >nul
set "ENVIRONMENT=development"
set "DATABASE_URL="
set "SUPABASE_DB_URL="
set "SUPABASE_URL="
set "SUPABASE_PUBLISHABLE_KEY="
set "SUPABASE_SECRET_KEY="

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload