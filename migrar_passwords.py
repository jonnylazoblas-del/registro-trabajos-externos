#!/usr/bin/env python3
"""
Migración (solo si ya tenías la versión anterior con contraseñas en texto plano):
convierte usuarios2.password -> usuarios2.password_hash.
Orden: sql/migracion_paso1.sql  ->  este script  ->  sql/migracion_paso2.sql
"""
from __future__ import annotations

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

URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
KEY = os.environ.get("SUPABASE_SECRET", "").strip()
if not URL or not KEY:
    sys.exit("Faltan SUPABASE_URL / SUPABASE_SECRET (.env)")

H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
     "Prefer": "return=representation"}

with httpx.Client(base_url=f"{URL}/rest/v1", headers=H, timeout=30.0) as c:
    r = c.get("/usuarios2", params={"select": "id,usuario,password,password_hash", "order": "id.asc"})
    r.raise_for_status()
    n = 0
    for u in r.json():
        if u.get("password_hash"):
            print(f"• {u['usuario']}: ya tiene hash")
            continue
        if not u.get("password"):
            print(f"✗ {u['usuario']}: sin contraseña, usa crear_usuarios.py --cambiar")
            continue
        p = c.patch("/usuarios2", params={"id": f"eq.{u['id']}"}, json={
            "password_hash": generate_password_hash(u["password"], method="pbkdf2:sha256"),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        })
        p.raise_for_status()
        n += 1
        print(f"✓ {u['usuario']}: migrado")
    print(f"Listo. Migrados: {n}. Ahora ejecuta sql/migracion_paso2.sql")
