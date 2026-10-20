#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
_user_site = Path.home() / ".local/lib/python3.12/site-packages"
if _user_site.exists() and str(_user_site) not in sys.path:
    sys.path.insert(0, str(_user_site))

"""
Crear usuarios en Supabase (tabla public.usuarios2 — NO toca public.usuarios)
Uso:
  python crear_usuarios.py --listar
  python crear_usuarios.py --seed
  python crear_usuarios.py --usuario ana --password Clave123 --nombre "Ana Pérez" --rol usuario
"""

import argparse
import os
import sys

import httpx

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://hpzqnqlaubgrwciljjzd.supabase.co"
).rstrip("/")
SUPABASE_SECRET = os.environ.get(
    "SUPABASE_SECRET", "sb_secret_B2kzCP_hqYb_x8qS_sjD3w__Ft6Av28"
)

HEADERS = {
    "apikey": SUPABASE_SECRET,
    "Authorization": f"Bearer {SUPABASE_SECRET}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

TABLE = "/usuarios2"

SEED_USERS = [
    {"usuario": "JonnyECC",     "password": "Jonny2030",      "nombre": "Jonny Lazo",          "rol": "admin"},
    {"usuario": "DianaECC",     "password": "Dianacesop",     "nombre": "Diana Julca",         "rol": "admin"},
    {"usuario": "SebastianECC", "password": "Sebastiancesop", "nombre": "Sebastian Astudillo", "rol": "admin"},
    {"usuario": "RogerECC",     "password": "Sebastiancesop", "nombre": "Roger Cumpa",         "rol": "admin"},
    {"usuario": "AngelEntel",   "password": "Angelentel",     "nombre": "Angel Entel",         "rol": "visor"},
    {"usuario": "ItaloEntel",   "password": "Italoentel",     "nombre": "Italo Entel",         "rol": "visor"},
]


def client():
    return httpx.Client(base_url=f"{SUPABASE_URL}/rest/v1", headers=HEADERS, timeout=30.0)


def listar():
    with client() as c:
        r = c.get(TABLE, params={"select": "id,usuario,nombre,rol,activo,created_at", "order": "id.asc"})
        if r.status_code == 404:
            print("La tabla usuarios2 no existe todavía.")
            print("Ejecuta supabase_schema.sql en el SQL Editor de Supabase.")
            return
        r.raise_for_status()
        rows = r.json()
        if not rows:
            print("No hay usuarios en usuarios2.")
            return
        print(f"{'ID':<6} {'USUARIO':<14} {'NOMBRE':<24} {'ROL':<10} ACTIVO")
        print("-" * 70)
        for u in rows:
            print(
                f"{u['id']:<6} {u['usuario']:<14} {(u.get('nombre') or ''):<24} "
                f"{(u.get('rol') or ''):<10} {u.get('activo', True)}"
            )


def crear(usuario: str, password: str, nombre: str, rol: str = "usuario"):
    rol = (rol or "usuario").lower()
    if rol not in ("admin", "usuario", "visor"):
        rol = "usuario"
    with client() as c:
        exists = c.get(TABLE, params={"select": "id", "usuario": f"eq.{usuario}", "limit": "1"})
        if exists.status_code == 404:
            print("ERROR: tabla usuarios2 no existe. Ejecuta supabase_schema.sql primero.")
            return False
        exists.raise_for_status()
        if exists.json():
            print(f"• Ya existe: {usuario} — se omite")
            return False
        r = c.post(
            TABLE,
            json={"usuario": usuario, "password": password, "nombre": nombre, "rol": rol, "activo": True},
        )
        r.raise_for_status()
        row = r.json()[0] if r.content else {}
        print(f"✓ Creado id={row.get('id')}  usuario={usuario}  nombre={nombre}  rol={rol}")
        return True


def seed():
    print("Creando usuarios en usuarios2 (solo los que no existan)...")
    ok = 0
    for u in SEED_USERS:
        if crear(u["usuario"], u["password"], u["nombre"], u.get("rol", "usuario")):
            ok += 1
    print(f"Listo. Nuevos creados: {ok}")


def main():
    ap = argparse.ArgumentParser(description="Gestionar usuarios2 en Supabase")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--usuario")
    ap.add_argument("--password")
    ap.add_argument("--nombre")
    ap.add_argument("--rol", default="usuario", help="admin o usuario")
    args = ap.parse_args()

    if args.listar:
        listar()
        return
    if args.seed:
        seed()
        return
    if args.usuario and args.password and args.nombre:
        crear(args.usuario, args.password, args.nombre, args.rol)
        return

    print("Tabla: public.usuarios2 (no afecta public.usuarios)\n")
    print("  python crear_usuarios.py --listar")
    print("  python crear_usuarios.py --seed")
    print('  python crear_usuarios.py --usuario ana --password Clave123 --nombre "Ana Pérez" --rol usuario')
    print()
    try:
        listar()
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
