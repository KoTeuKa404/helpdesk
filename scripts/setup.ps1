# Generate local secrets. Does not overwrite an existing .env.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root '.env'
$template = Join-Path $root '.env.example'
if (Test-Path -LiteralPath $target) { Write-Host '.env already exists; leaving it unchanged.'; exit 0 }
if (-not (Test-Path -LiteralPath $template)) { throw 'Missing .env.example' }
function New-SecureValue([int]$count = 48) {
    $buffer = New-Object byte[] $count
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+','-').Replace('/','_')
}
$values = @{
  'DJANGO_SECRET_KEY' = New-SecureValue 48
  'POSTGRES_PASSWORD' = New-SecureValue 32
  'WEBHOOK_SECRET' = New-SecureValue 40
  'OPERATOR_PASSWORD' = New-SecureValue 24
  'ADMINROOT_PASSWORD' = New-SecureValue 24
}
$out = [IO.File]::ReadAllText($template)
foreach ($key in $values.Keys) {
  $pattern = '(?m)^' + [regex]::Escape($key) + '=.*$'
  $out = [regex]::Replace($out, $pattern, ($key + '=' + $values[$key]))
}
[IO.File]::WriteAllText($target, $out, (New-Object System.Text.UTF8Encoding $false))
Write-Host 'Created .env with random secrets. Passwords were NOT printed.'
Write-Host 'Operator username: operator'
Write-Host 'Admin username: adminroot'
Write-Host 'For login credentials inspect .env locally. Never commit it to Git.'
