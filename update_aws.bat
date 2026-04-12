@echo off
:: ==========================================
:: TAZA KHABAR - ONE-CLICK AWS UPDATE
:: ==========================================

:: 1. SETTINGS (Change these to match your setup)
set AWS_IP=13.48.1.16
set PEM_NAME=your-key.pem
set REMOTE_DIR=Taza-khabar/backend

echo [1/3] Pushing latest code to GitHub...
git add .
git commit -m "Auto-update from laptop"
git push origin main

echo.
echo [2/3] Connecting to AWS and pulling new code...
:: This runs commands on the AWS server remotely
ssh -o StrictHostKeyChecking=no -i "%PEM_NAME%" ec2-user@%AWS_IP% "cd %REMOTE_DIR% && git pull origin main"

echo.
echo [3/3] Restarting the Docker container...
ssh -o StrictHostKeyChecking=no -i "%PEM_NAME%" ec2-user@%AWS_IP% "sudo docker stop news-server news-live || true && sudo docker rm news-server news-live || true && cd %REMOTE_DIR% && sudo docker build -t news-backend . && sudo docker run -d -p 8000:8000 --name news-server news-backend"

echo.
echo ==========================================
echo ✅ AWS SERVER UPDATED SUCCESSFULLY!
echo ==========================================
pause
