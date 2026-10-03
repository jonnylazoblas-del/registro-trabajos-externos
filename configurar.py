#!/usr/bin/env python3
"""
Asistente de configuración: crea el archivo .env y prueba la conexión a Supabase.
Colócalo en la carpeta del proyecto (junto a app.py) y ejecuta:  python configurar.py
"""
import getpass
import secrets
import sys
from pathlib import Path

import httpx

CARPETA = Path(__file__).resolve().parent
ENV = CARPETA / ".env"
URL_DEFECTO = "https://hpzqnqlaubgrwciljjzd.supabase.co"

print("=" * 58)
print("  Configuración — Registro de Trabajos Externos")
print("=" * 58)

if not (CARPETA / "app.py").exists():
    sys.exit("\n✗ Este archivo debe estar en la misma carpeta que app.py.")

if ENV.exists():
    if input("\nYa existe un archivo .env. ¿Reemplazarlo? (s/n): ").strip().lower() != "s":
        sys.exit("Sin cambios.")

print("\nEn Supabase copia tu secret key NUEVA con el botón de copiar")
print("(Project Settings -> API Keys) y pégala aquí (clic derecho).")
print("No se mostrará mientras la pegas.\n")
clave = getpass.getpass("Secret key: ").strip().strip('"').strip("'")

if not clave.startswith("sb_secret_") or " " in clave or len(clave) < 30:
    sys.exit("\n✗ No parece una secret key completa (debe empezar con sb_secret_). "
             "Cópiala de nuevo con el botón de copiar e inténtalo otra vez.")
print(f"✓ Recibida: {clave[:14]}…{clave[-4:]}  ({len(clave)} caracteres)")

ENV.write_text(
    "# Generado por configurar.py. NO subas este archivo a ningún repositorio.\n"
    f"SUPABASE_URL={URL_DEFECTO}\n"
    f"SUPABASE_SECRET={clave}\n"
    f"SECRET_KEY={secrets.token_hex(32)}\n"
    "COOKIE_SECURE=0\n"
    "TRUST_PROXY=0\n"
    "HOST=127.0.0.1\n"
    "PORT=5050\n",
    encoding="utf-8",
)
print("✓ Archivo .env creado con una SECRET_KEY aleatoria nueva.")

print("\nProbando conexión con Supabase...")
try:
    r = httpx.get(
        f"{URL_DEFECTO}/rest/v1/usuarios2",
        params={"select": "id", "limit": "1"},
        headers={"apikey": clave, "Authorization": f"Bearer {clave}"},
        timeout=20,
    )
except Exception as e:
    sys.exit(f"✗ No se pudo conectar: {e}\n  Revisa tu internet e inténtalo de nuevo.")

if r.status_code == 200:
    print("✓ Conexión correcta. La clave funciona y la tabla usuarios2 existe.")
elif r.status_code in (401, 403):
    print("✗ Supabase rechazó la clave. Cópiala de nuevo con el botón de copiar y repite.")
elif r.status_code == 404:
    print("✓ La clave funciona, pero aún no existe la tabla usuarios2.")
    print("  Ejecuta primero el SQL (instalación nueva: sql/supabase_schema.sql).")
else:
    print(f"? Respuesta inesperada ({r.status_code}): {r.text[:200]}")

print("\nListo. Siguiente paso: la migración de la base de datos (paso 4).")
