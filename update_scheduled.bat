@echo off
rem Run by the "FantasyRankingsDailyUpdate" scheduled task (see schedule_update.ps1). No pause, so it can run unattended.
rem Output of the latest run is saved to data\update.log.
cd /d "%~dp0"
set "PY=C:\Python314\python.exe"
if not exist "%PY%" set "PY=python"
echo Run started %date% %time% > data\update.log
"%PY%" update_data.py >> data\update.log 2>&1
echo Exit code %errorlevel% >> data\update.log
