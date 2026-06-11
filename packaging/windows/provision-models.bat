@echo off
setlocal
cd /d "%~dp0"
rem One-time, network-required: cache the local embedding model so the
rem contract-verification wedge works fully offline afterwards. The
rem citation/quote wedge works without this step.
if not exist ".venv\Scripts\python.exe" (
  echo Run run-cachet.bat once first to set up the environment.
  pause
  exit /b 1
)
echo Downloading the local embedding model (~130 MB, one time)...
set "CARREL_FASTEMBED_CACHE_DIR=%USERPROFILE%\.cache\carrel-fastembed"
set "HF_HUB_OFFLINE=0"
".venv\Scripts\python.exe" -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir=r'%USERPROFILE%\.cache\carrel-fastembed')" && echo Done. Cachet's contract checks now run fully offline.
pause
