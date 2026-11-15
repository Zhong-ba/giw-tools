@echo off
rem Previews the public site locally: builds the frontend and serves it with the backend in hosted mode, so tools,
rem browser-kept jobs and the dataset picker behave like the deployed site, using this computer's prepared data.
rem Usage: previewSite.bat [--port 8010] [--nobuild]
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
set "port=8010"
set "build=1"
:args
if "%~1"=="" goto run
if /i "%~1"=="--nobuild" (set "build=0" & shift & goto args)
if /i "%~1"=="--port" (set "port=%~2" & shift & shift & goto args)
echo Unknown option %1
popd
exit /b 2
:run
if "%build%"=="1" (
    rem An empty VITE_API_URL makes the page call the API on the same address it is served from.
    set "VITE_API_URL="
    call npm.cmd --prefix frontend run build
    if errorlevel 1 (
        set "preview_exit=1"
        goto done
    )
)
echo.
echo Site preview: http://127.0.0.1:%port%  (Ctrl+C to stop)
rem Open the browser once the server has had a moment to start.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://127.0.0.1:%port%'"
python -m webui --hosted --port %port%
set "preview_exit=%errorlevel%"
:done
popd
exit /b %preview_exit%
