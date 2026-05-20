"""
Obtiene el refresh token de Google OAuth2 para Gmail, Calendar y Drive.

Uso:
  1. Descargá credentials.json desde Google Cloud Console
     (APIs & Services → Credentials → tu OAuth 2.0 Client → Download JSON)
  2. Colocá credentials.json en la misma carpeta que este script
  3. Ejecutá: python scripts/get_google_tokens.py
  4. Se abre el browser, autenticás con tu cuenta de Google
  5. El script imprime los valores para pegar en .env

Dependencia (una sola vez):
  pip install google-auth-oauthlib
"""

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Falta la dependencia. Instalá con:\n  pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
]

credentials_path = Path(__file__).parent / "credentials.json"
if not credentials_path.exists():
    print(f"No encontré credentials.json en {credentials_path}")
    print("Descargalo desde: console.cloud.google.com → APIs & Services → Credentials")
    sys.exit(1)

print("Abriendo el browser para autenticarte con Google...")
flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes=SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

print("\n" + "=" * 60)
print("Pegá estos valores en tu .env:")
print("=" * 60)
print(f"GOOGLE_CLIENT_ID={creds.client_id}")
print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
print("=" * 60)
print("\nEl refresh token NO vence. Guardalo bien.")
