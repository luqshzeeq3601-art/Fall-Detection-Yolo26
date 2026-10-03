@echo off
rem Launches the ElderCare Vision API (:8000) and React dashboard (:5173), then opens the browser.
setlocal
cd /d "%~dp0"

where uv >nul 2>&1 || (echo [ERROR] uv not found on PATH. & pause & exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] npm not found on PATH. & pause & exit /b 1)

if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    pushd frontend
    call npm install || (echo [ERROR] npm install failed. & popd & pause & exit /b 1)
    popd
)

echo Starting backend  on http://127.0.0.1:8000 ...
start "ElderCare API" cmd /k "cd /d "%~dp0" && uv run uvicorn eldercare.api.server:create_server_app --factory --host 127.0.0.1 --port 8000"

echo Starting frontend on http://127.0.0.1:5173 ...
start "ElderCare Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"

echo Waiting for the API to come up...
set /a tries=0
:wait
curl -s -o nul http://127.0.0.1:8000/docs && goto ready
set /a tries+=1
if %tries% geq 90 (echo [WARN] API did not respond after 90s; opening browser anyway. & goto ready)
timeout /t 1 /nobreak >nul
goto wait

:ready
start "" http://127.0.0.1:5173
echo.
echo Running. Close the "ElderCare API" and "ElderCare Frontend" windows to stop.
timeout /t 5 >nul
