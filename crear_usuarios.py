#!/usr/bin/env python3
"""
Gestión de usuarios (tabla public.usuarios2). Las contraseñas se guardan con hash.

  python crear_usuarios.py --listar
  python crear_usuarios.py --seed                       # crea los de usuarios_iniciales.json
  python crear_usuarios.py --usuario ana --nombre "Ana Pérez" --rol usuario [--password X]
  python crear_usuarios.py --cambiar RogerECC [--password X]   # restablecer contraseña
  python crear_usuarios.py --activar ana | --desactivar ana

Si no pasas --password, se pide por teclado (no queda en el historial).
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from werkzeug.security import generate_password_hash

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SECRET = os.environ.get("SUPABASE_SECRET", "").strip()
if not SUPABASE_URL or not SUPABASE_SECRET:
    sys.exit("Faltan SUPABASE_URL / SUPABASE_SECRET (archivo .env, ver LEEME.txt).")

HASH_METHOD = "pbkdf2:sha256"
MIN_PASSWORD = 8
ROLES = ("admin", "usuario", "visor")
TABLE = "/usuarios2"
SEED_FILE = Path(__file__).with_name("usuarios_iniciales.json")

HEADERS = {
    "apikey": SUPABASE_SECRET,
    "Authorization": f"Bearer {SUPABASE_SECRET}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def client():
    return httpx.Client(base_url=f"{SUPABASE_URL}/rest/v1", headers=HEADERS, timeout=30.0)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def pedir_password(usuario: str) -> str:
    while True:
        p1 = getpass.getpass(f"Nueva contraseña para {usuario}: ")
        if len(p1) < MIN_PASSWORD:
            print(f"  Mínimo {MIN_PASSWORD} caracteres.")
            continue
        if p1 != getpass.getpass("Repite la contraseña: "):
            print("  No coinciden.")
            continue
        return p1


def listar():
    with client() as c:
        r = c.get(TABLE, params={"select": "id,usuario,nombre,rol,activo", "order": "id.asc"})
        if r.status_code == 404:
            print("La tabla usuarios2 no existe. Ejecuta sql/supabase_schema.sql en Supabase.")
            return
        r.raise_for_status()
        rows = r.json()
        if not rows:
            print("No hay usuarios en usuarios2.")
            return
        print(f"{'ID':<5} {'USUARIO':<14} {'NOMBRE':<24} {'ROL':<9} ACTIVO")
        print("-" * 64)
        for u in rows:
            print(f"{u['id']:<5} {u['usuario']:<14} {(u.get('nombre') or ''):<24} {(u.get('rol') or ''):<9} {u.get('activo', True)}")


def crear(usuario: str, password: str, nombre: str, rol: str = "usuario") -> bool:
    rol = (rol or "usuario").lower()
    if rol not in ROLES:
        rol = "usuario"
    if len(password) < MIN_PASSWORD:
        print(f"✗ {usuario}: la contraseña debe tener al menos {MIN_PASSWORD} caracteres")
        return False
    with client() as c:
        ex = c.get(TABLE, params={"select": "id", "usuario": f"eq.{usuario}", "limit": "1"})
        if ex.status_code == 404:
            print("ERROR: tabla usuarios2 no existe. Ejecuta sql/supabase_schema.sql primero.")
            return False
        ex.raise_for_status()
        if ex.json():
            print(f"• Ya existe: {usuario} — se omite (usa --cambiar para su contraseña)")
            return False
        r = c.post(TABLE, json={
            "usuario": usuario,
            "password_hash": generate_password_hash(password, method=HASH_METHOD),
            "nombre": nombre, "rol": rol, "activo": True,
            "password_changed_at": now_iso(),
        })
        r.raise_for_status()
        row = r.json()[0] if r.content else {}
        print(f"✓ Creado id={row.get('id')}  usuario={usuario}  rol={rol}")
        return True


def cambiar(usuario: str, password: str | None):
    password = password or pedir_password(usuario)
    if len(password) < MIN_PASSWORD:
        print(f"✗ Mínimo {MIN_PASSWORD} caracteres")
        return
    with client() as c:
        r = c.patch(TABLE, params={"usuario": f"eq.{usuario}"}, json={
            "password_hash": generate_password_hash(password, method=HASH_METHOD),
            "password_changed_at": now_iso(),
        })
        r.raise_for_status()
        print(f"✓ Contraseña actualizada: {usuario}" if r.json() else f"✗ No existe el usuario {usuario}")


def activar(usuario: str, valor: bool):
    with client() as c:
        r = c.patch(TABLE, params={"usuario": f"eq.{usuario}"}, json={"activo": valor})
        r.raise_for_status()
        print(f"✓ {usuario}: activo={valor}" if r.json() else f"✗ No existe el usuario {usuario}")


def seed():
    if not SEED_FILE.exists():
        sys.exit(f"No existe {SEED_FILE.name}")
    users = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    print("Creando usuarios iniciales (solo los que no existan)...")
    n = sum(1 for u in users if crear(u["usuario"], u["password"], u["nombre"], u.get("rol", "usuario")))
    print(f"Listo. Nuevos creados: {n}")
    print("Recomendado: borra usuarios_iniciales.json y pide a cada persona cambiar su contraseña desde la app.")


def main():
    ap = argparse.ArgumentParser(description="Gestionar usuarios2 en Supabase")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--usuario")
    ap.add_argument("--password")
    ap.add_argument("--nombre")
    ap.add_argument("--rol", default="usuario", help="admin | usuario | visor")
    ap.add_argument("--cambiar", metavar="USUARIO", help="restablecer contraseña")
    ap.add_argument("--activar", metavar="USUARIO")
    ap.add_argument("--desactivar", metavar="USUARIO")
    a = ap.parse_args()

    if a.listar:
        listar()
    elif a.seed:
        seed()
    elif a.cambiar:
        cambiar(a.cambiar, a.password)
    elif a.activar:
        activar(a.activar, True)
    elif a.desactivar:
        activar(a.desactivar, False)
    elif a.usuario and a.nombre:
        crear(a.usuario, a.password or pedir_password(a.usuario), a.nombre, a.rol)
    else:
        ap.print_help()


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as e:
        sys.exit(f"Error de conexión con Supabase: {e}")
