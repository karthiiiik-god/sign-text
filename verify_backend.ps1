# Verify backend
Write-Host "Checking port 8003..."
netstat_result = netstat -an | Select-String "8003"
if ($netstat_result) { Write-Host "✓ Backend listening" -ForegroundColor Green } else { Write-Host "✗ No server" -ForegroundColor Red }
$response = Invoke-RestMethod -Uri "http://127.0.0.1:8003/health" -Method Get -ErrorAction SilentlyContinue
if ($response) { Write-Host "✓ API OK: $($response | ConvertTo-Json)" -ForegroundColor Green } else { Write-Host "✗ API unreachable" -ForegroundColor Red }
