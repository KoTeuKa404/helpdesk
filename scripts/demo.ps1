# Sends one event, then you can review it in the operator dashboard.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Run scripts/setup.ps1 first.' }
$secretLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^WEBHOOK_SECRET=' } | Select-Object -First 1
if (-not $secretLine) { throw 'WEBHOOK_SECRET is not configured' }
$secret = $secretLine.Substring('WEBHOOK_SECRET='.Length)
$id = 'T-' + (Get-Random -Minimum 100000 -Maximum 999999)
$payload = @{
    event_id = 'evt-' + [guid]::NewGuid().ToString('N')
    ticket_id = $id
    customer_email = 'user@example.com'
    message = 'Не можу експортувати звіт у PDF'
    reply_url = "http://mock-helpdesk:8001/tickets/$id/replies"
}
$json = $payload | ConvertTo-Json -Compress
$body = [Text.Encoding]::UTF8.GetBytes($json)
$result = Invoke-RestMethod -Uri 'http://127.0.0.1:8020/webhooks/helpdesk' -Method Post `
    -Headers @{ 'X-Webhook-Secret' = $secret } -ContentType 'application/json; charset=utf-8' -Body $body
Write-Host ('Webhook accepted for ticket ' + $id)
$result | ConvertTo-Json
Write-Host 'Log into http://127.0.0.1:8020/ to review/approve the draft.'
