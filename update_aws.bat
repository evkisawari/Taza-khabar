@echo off
:: ==========================================
:: TAZA KHABAR - ONE-CLICK AWS UPDATE
:: ==========================================

:: 1. SETTINGS
set AWS_IP=13.48.1.16
set PEM_NAME=news-key.pem
set REMOTE_DIR=Taza-khabar/backend
set SSH_PATH=C:\Windows\System32\OpenSSH\ssh.exe

echo [1/3] Pushing latest code to GitHub...
git add .
git commit -m "Auto-update from laptop"
git push origin main

echo.
echo [2/3] Connecting to AWS and pulling new code...
"%SSH_PATH%" -o StrictHostKeyChecking=no -i "%PEM_NAME%" ec2-user@%AWS_IP% "cd %REMOTE_DIR% && git pull origin main"

echo.
echo [3/3] Restarting the Docker container...
"%SSH_PATH%" -o StrictHostKeyChecking=no -i "%PEM_NAME%" ec2-user@%AWS_IP% "sudo docker stop news-server news-live || true && sudo docker rm news-server news-live || true && cd %REMOTE_DIR% && sudo docker build -t news-backend . && sudo docker run -d -p 8000:8000 --name news-server news-backend"

echo.
echo ==========================================
echo ✅ AWS SERVER UPDATED SUCCESSFULLY!
echo ==========================================
pause
