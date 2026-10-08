@echo off
cd /d C:\Users\63054\.agents\skills\daily-briefing-pro
python inline_runner.py > data\run_output.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> data\run_output.txt
