@echo off
title Autonomous LinkedIn AI Agent - Scheduler
echo ========================================================
echo   AUTONOMOUS LINKEDIN JOB SEARCH & EMAIL AGENT
echo ========================================================
echo Starting 24/7 background scheduler...
echo The agent will run the complete pipeline daily at 18:00.
echo.
python agent.py schedule
pause
