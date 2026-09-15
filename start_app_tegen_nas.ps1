# Start de Teeltregistratie-app lokaal tegen de PostgreSQL op de NAS.
# De Supabase-database wordt hierbij niet gebruikt.
#
# Wachtwoord staat in .env.nas (buiten git gehouden).

function Import-EnvBestand($pad, $sleutels) {
    Get-Content $pad | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*"?([^"\r\n]+)"?') {
            if (-not $sleutels -or $sleutels -contains $matches[1]) {
                Set-Item -Path "env:$($matches[1])" -Value $matches[2]
            }
        }
    }
}

Import-EnvBestand 'C:\Users\Job\OneDrive\Python\.env.nas' @('DATABASE_URL')
Import-EnvBestand 'C:\Users\Job\Downloads\VEMteelt.env' @('AUTH_COOKIE_KEY', 'PRIVA_CLIENT_ID', 'PRIVA_CLIENT_SECRET')

if (-not $env:DATABASE_URL) { throw "DATABASE_URL niet gevonden in .env.nas" }

Set-Location 'C:\Users\Job\OneDrive\Python'
streamlit run app.py --server.port 8501 --server.headless true
