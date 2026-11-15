@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
python -m webui %*
set "webui_exit=%errorlevel%"
popd
exit /b %webui_exit%
