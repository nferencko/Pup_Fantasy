@echo off
rem Run by the "FantasyRankingsDailyUpdate" scheduled task (see schedule_update.ps1). No pause, so it can run unattended.
rem Output of the latest run is saved to data\update.log.
cd /d "%~dp0"
set "PY=C:\Python314\python.exe"
if not exist "%PY%" set "PY=python"
echo Run started %date% %time% > data\update.log
"%PY%" update_data.py >> data\update.log 2>&1
echo Exit code %errorlevel% >> data\update.log
rem Publish to GitHub Pages: commit and push data.js only if the update succeeded and the data changed.
if not "%errorlevel%"=="0" goto :eof
git add data/data.js >> data\update.log 2>&1
git diff --cached --quiet && (echo No data changes to publish. >> data\update.log & goto :eof)
git commit -m "Update rankings data" >> data\update.log 2>&1
git pull --rebase --autostash -X theirs >> data\update.log 2>&1
git push >> data\update.log 2>&1
echo Push exit code %errorlevel% >> data\update.log
