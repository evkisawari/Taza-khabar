# ==========================================
# TAZA KHABAR - POWERSHELL AWS UPDATE
# ==========================================

$AWS_IP = "13.48.1.16"
$PEM_NAME = "news-key.pem"
$REMOTE_DIR = "Taza-khabar/backend"
$SSH_EXE = "C:\Windows\System32\OpenSSH\ssh.exe"

Write-Host "[1/4] Fixing Key Permissions..." -ForegroundColor Cyan
# Using icacls directly as it's more reliable
& icacls "$PEM_NAME" /inheritance:r | Out-Null
& icacls "$PEM_NAME" /grant:r "$($env:USERNAME):R" | Out-Null

Write-Host "`n[2/4] Pushing latest code to GitHub..." -ForegroundColor Cyan
git add .
git commit -m "Auto-update from laptop"
git push origin main

Write-Host "`n[3/4] Connecting to AWS and pulling new code..." -ForegroundColor Cyan
$sshKeyPath = (Resolve-Path $PEM_NAME).Path
& "$SSH_EXE" -o StrictHostKeyChecking=no -i "$sshKeyPath" ec2-user@$AWS_IP "cd $REMOTE_DIR && git pull origin main"

Write-Host "`n[4/4] Restarting the Docker container..." -ForegroundColor Cyan
& "$SSH_EXE" -o StrictHostKeyChecking=no -i "$sshKeyPath" ec2-user@$AWS_IP "sudo docker stop news-server news-live ; sudo docker rm news-server news-live ; cd $REMOTE_DIR && sudo docker build -t news-backend . && sudo docker run -d -p 8000:8000 --name news-server news-backend"

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "✅ AWS SERVER UPDATED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Pause
