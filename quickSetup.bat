@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
py setupData.py %*
set "setup_exit=%errorlevel%"
popd
exit /b %setup_exit%