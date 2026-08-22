@echo off
REM ---------------------------------------------------------------------------
REM Raj Local Agent launcher (Windows).
REM
REM Edit RAJ_HOME / PYTHON below to match your install, then either:
REM   * double-click this file to run the agent in a console, or
REM   * register it as a Windows service with NSSM (see INSTALL_WINDOWS.md).
REM ---------------------------------------------------------------------------

set "RAJ_HOME=%~dp0.."
set "PYTHON=%RAJ_HOME%\.venv\Scripts\python.exe"

REM Fall back to the system Python if no venv exists.
if not exist "%PYTHON%" set "PYTHON=python"

cd /d "%RAJ_HOME%"
"%PYTHON%" -m raj_monitor.agent --config "%RAJ_HOME%\config.yaml"
