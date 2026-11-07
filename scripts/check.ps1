$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  docker compose ps
  docker compose exec web python manage.py check
  docker compose exec web python manage.py test tests --verbosity 2
} finally { Pop-Location }
