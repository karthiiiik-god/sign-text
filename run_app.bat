@echo off
echo Starting SignCall Backend...
start "Backend" cmd /k "uvicorn main:app --host 127.0.0.1 --port 8003 --reload"
timeout /t 3 /nobreak >nul
echo Starting Streamlit Frontend...
start "Frontend" cmd /k "streamlit run app.py"
echo App ready! Backend: http://127.0.0.1:8003  Frontend: auto-opens in browser
pause
