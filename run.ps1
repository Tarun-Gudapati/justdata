# Clean launcher for the Streamlit app.
# Kills anything already on port 8501, then starts ONE fresh server.
# Usage:  .\run.ps1

$port = 8501

Write-Host "Freeing port $port ..."
for ($i = 0; $i -lt 10; $i++) {
    $owner = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess
    if ($owner) {
        Write-Host "  killing lingering process $owner"
        taskkill /PID $owner /F 2>$null | Out-Null
        Start-Sleep -Milliseconds 800
    }
    else { break }
}

# Clear stale bytecode so code changes always take effect.
Remove-Item -Recurse -Force "__pycache__" -ErrorAction SilentlyContinue

Write-Host "Starting Streamlit on http://localhost:$port ..."
& ".\.venv\Scripts\python.exe" -m streamlit run app.py --server.port $port
