#!/usr/bin/env python3
"""
Registro de Trabajos Externos — CESOP Hogar · Entel
Backend Flask + Supabase (REST).  Diseñado y Publicado por Jonny Lazo (CESOP)

Configuración: variables de entorno o archivo .env (ver .env.example).
"""
from __future__ import annotations

import os
import secrets
import sys
import time
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

import httpx
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

try:  # .env es opcional
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

# ── Configuración ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SECRET = os.environ.get("SUPABASE_SECRET", "").strip()
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()

_faltan = [
    n
    for n, v in (
        ("SUPABASE_URL", SUPABASE_URL),
        ("SUPABASE_SECRET", SUPABASE_SECRET),
        ("SECRET_KEY", SECRET_KEY),
    )
    if not v
]
if _faltan:
    sys.exit(
        "Faltan variables de entorno: "
        + ", ".join(_faltan)
        + "\nCopia .env.example a .env y complétalo (ver LEEME.txt)."
    )

HASH_METHOD = "pbkdf2:sha256"
MIN_PASSWORD = 8
ROLES = ("admin", "usuario", "visor")
MAX_BULK = 5000

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
)
if os.environ.get("TRUST_PROXY", "0") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

_http = httpx.Client(
    base_url=f"{SUPABASE_URL}/rest/v1",
    headers={
        "apikey": SUPABASE_SECRET,
        "Authorization": f"Bearer {SUPABASE_SECRET}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    },
    timeout=30.0,
)

# Hash falso para igualar el tiempo de respuesta cuando el usuario no existe
_DUMMY_HASH = generate_password_hash(secrets.token_hex(8), method=HASH_METHOD)


# ── Helpers Supabase ────────────────────────────────────────────────────────
def sb_get(path: str, **params):
    r = _http.get(path, params=params)
    r.raise_for_status()
    return r.json()


def sb_get_all(path: str, page: int = 1000, **params):
    """Trae TODAS las filas (Supabase corta en 1000 por consulta)."""
    out: list = []
    offset = 0
    while True:
        chunk = sb_get(path, limit=str(page), offset=str(offset), **params)
        out.extend(chunk)
        if len(chunk) < page:
            break
        offset += page
    return out


def sb_post(path: str, body):
    r = _http.post(path, json=body)
    r.raise_for_status()
    if r.status_code == 204 or not r.content:
        return None
    return r.json()


def sb_patch(path: str, body, **params):
    r = _http.patch(path, params=params, json=body)
    r.raise_for_status()
    if r.status_code == 204 or not r.content:
        return None
    return r.json()


def sb_delete(path: str, **params):
    r = _http.delete(path, params=params)
    r.raise_for_status()
    return True


def http_msg(e: Exception) -> str:
    resp = getattr(e, "response", None)
    return resp.text[:300] if resp is not None else str(e)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Límite de intentos (en memoria, por proceso) ────────────────────────────
_FAILS: dict[str, list[float]] = {}
MAX_FAILS = 5
FAIL_WINDOW = 600  # segundos


def rate_limited(key: str) -> bool:
    now = time.time()
    lst = [t for t in _FAILS.get(key, []) if now - t < FAIL_WINDOW]
    _FAILS[key] = lst
    return len(lst) >= MAX_FAILS


def register_fail(key: str) -> None:
    _FAILS.setdefault(key, []).append(time.time())


def clear_fails(key: str) -> None:
    _FAILS.pop(key, None)


# ── Sesión y permisos ───────────────────────────────────────────────────────
def safe_next(target: str | None) -> str:
    """Solo rutas internas (evita open redirect, incluido //sitio.com)."""
    default = url_for("index")
    if not target or not target.startswith("/") or target.startswith("//"):
        return default
    if "\\" in target:
        return default
    p = urlparse(target)
    if p.scheme or p.netloc:
        return default
    return target


def refresh_user() -> bool:
    """Revalida cada 60 s que el usuario siga activo y actualiza su rol."""
    uid = session.get("user_id")
    if not uid:
        return False
    if time.time() - session.get("chk", 0) < 60:
        return True
    try:
        rows = sb_get(
            "/usuarios2",
            select="id,nombre,rol,activo",
            id=f"eq.{uid}",
            limit="1",
        )
    except Exception:
        return True  # caída transitoria de Supabase: no expulsar a nadie
    if not rows or rows[0].get("activo") is False:
        session.clear()
        return False
    session["rol"] = rows[0].get("rol") or "usuario"
    session["nombre"] = rows[0].get("nombre") or session.get("username")
    session["chk"] = time.time()
    return True


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not refresh_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "No autenticado"}), 401
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


def current_user():
    if not session.get("user_id"):
        return None
    return {
        "id": session["user_id"],
        "username": session.get("username"),
        "nombre": session.get("nombre"),
        "rol": session.get("rol", "usuario"),
    }


def is_admin() -> bool:
    return session.get("rol") == "admin"


def can_write() -> bool:
    """admin y usuario escriben; visor solo ve y exporta."""
    return session.get("rol") in ("admin", "usuario")


def can_edit_row(row: dict) -> bool:
    """admin edita todo; usuario solo lo que él registró."""
    if not can_write():
        return False
    return is_admin() or row.get("user_id") == session.get("user_id")


def validate_new_password(pw: str, username: str = "") -> str | None:
    if len(pw) < MIN_PASSWORD:
        return f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres"
    if username and pw.lower() == username.lower():
        return "La contraseña no puede ser igual al usuario"
    return None


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    if request.endpoint == "static":
        resp.headers["Cache-Control"] = "public, max-age=3600"
    else:
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return resp


# ── Login / logout ──────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id") and refresh_user():
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        key = f"login|{request.remote_addr}|{username.lower()}"

        if rate_limited(key):
            error = "Demasiados intentos fallidos. Espera 10 minutos e inténtalo de nuevo."
        else:
            rows = None
            try:
                rows = sb_get(
                    "/usuarios2",
                    select="id,usuario,password_hash,nombre,rol,activo",
                    usuario=f"eq.{username}",
                    limit="1",
                )
            except Exception:
                error = "No se pudo conectar con la base de datos. Revisa Supabase."

            if error is None:
                u = rows[0] if rows else None
                hash_ = (u or {}).get("password_hash") or _DUMMY_HASH
                ok = check_password_hash(hash_, password) and u is not None
                if not ok:
                    register_fail(key)
                    error = "Usuario o contraseña incorrectos."
                elif u.get("activo") is False:
                    error = "Usuario desactivado. Contacta al administrador."
                else:
                    clear_fails(key)
                    session.clear()
                    session.permanent = True
                    session["user_id"] = u["id"]
                    session["username"] = u["usuario"]
                    session["nombre"] = u.get("nombre") or u["usuario"]
                    session["rol"] = u.get("rol") or "usuario"
                    session["chk"] = time.time()
                    return redirect(safe_next(request.args.get("next")))

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user())


@app.route("/api/me")
@login_required
def api_me():
    return jsonify(current_user())


# ── Contraseña propia ───────────────────────────────────────────────────────
@app.route("/api/me/password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json(silent=True) or {}
    actual = str(data.get("actual") or "")
    nueva = str(data.get("nueva") or "")
    uid = session["user_id"]
    key = f"pw|{uid}"

    if rate_limited(key):
        return jsonify({"error": "Demasiados intentos. Espera 10 minutos."}), 429
    err = validate_new_password(nueva, session.get("username", ""))
    if err:
        return jsonify({"error": err}), 400
    if nueva == actual:
        return jsonify({"error": "La nueva contraseña debe ser distinta de la actual"}), 400

    try:
        rows = sb_get("/usuarios2", select="id,password_hash", id=f"eq.{uid}", limit="1")
        if not rows or not check_password_hash(rows[0].get("password_hash") or "", actual):
            register_fail(key)
            return jsonify({"error": "La contraseña actual es incorrecta"}), 400
        sb_patch(
            "/usuarios2",
            {
                "password_hash": generate_password_hash(nueva, method=HASH_METHOD),
                "password_changed_at": now_iso(),
            },
            id=f"eq.{uid}",
        )
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    clear_fails(key)
    return jsonify({"ok": True})


# ── Registros ───────────────────────────────────────────────────────────────
REC_KEYS = (
    "fecha", "orden", "tipoorden", "codigo", "tiposerv", "tipo",
    "area", "resultado", "accion", "red", "focal", "obs",
)


def row_to_dict(r: dict) -> dict:
    fecha = r.get("fecha") or ""
    if isinstance(fecha, str) and "T" in fecha:
        fecha = fecha[:10]
    d = {
        "id": r.get("id"),
        "nro": r.get("nro"),
        "fecha": fecha,
        "creado": r.get("creado"),
        "editable": can_edit_row(r),
    }
    for k in REC_KEYS:
        if k != "fecha":
            d[k] = r.get(k) or ""
    return d


def clean_record(data: dict, lenient: bool = False):
    """Normaliza un registro. Devuelve (body, error)."""
    area = str(data.get("area") or "").strip()
    focal = str(data.get("focal") or "").strip()
    if not area and lenient:
        area = "Importado"
    if not area:
        return None, "Área Solicitante es obligatoria"
    if not focal:
        return None, "Focal Responsable es obligatorio"

    fecha = str(data.get("fecha") or "")[:10]
    try:
        date.fromisoformat(fecha)
    except ValueError:
        fecha = date.today().isoformat()

    def s(k, default=""):
        return str(data.get(k) or default).strip()

    return {
        "fecha": fecha,
        "orden": s("orden"),
        "tipoorden": s("tipoorden"),
        "codigo": s("codigo"),
        "tiposerv": s("tiposerv", "Hogar"),
        "tipo": s("tipo", "Otro"),
        "area": area,
        "resultado": s("resultado"),
        "accion": s("accion"),
        "red": s("red"),
        "focal": focal,
        "obs": s("obs"),
    }, None


def get_trabajo(tid: str):
    rows = sb_get("/trabajos_externos", select="*", id=f"eq.{tid}", limit="1")
    return rows[0] if rows else None


@app.route("/api/trabajos", methods=["GET"])
@login_required
def api_list():
    try:
        rows = sb_get_all("/trabajos_externos", select="*", order="fecha.desc,nro.desc")
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            return jsonify({"error": "Tabla trabajos_externos no existe. Ejecuta sql/supabase_schema.sql."}), 500
        return jsonify({"error": http_msg(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/trabajos", methods=["POST"])
@login_required
def api_create():
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    body, err = clean_record(request.get_json(silent=True) or {})
    if err:
        return jsonify({"error": err}), 400
    body["id"] = "r" + secrets.token_hex(8)
    body["user_id"] = session.get("user_id")  # nro lo asigna la secuencia de la BD
    try:
        rows = sb_post("/trabajos_externos", body)
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    row = rows[0] if isinstance(rows, list) and rows else body
    return jsonify(row_to_dict(row)), 201


@app.route("/api/trabajos/bulk", methods=["POST"])
@login_required
def api_bulk():
    """Importación masiva: un solo viaje, omite duplicados exactos."""
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    regs = (request.get_json(silent=True) or {}).get("registros")
    if not isinstance(regs, list) or not regs:
        return jsonify({"error": "No hay registros para importar"}), 400
    if len(regs) > MAX_BULK:
        return jsonify({"error": f"Máximo {MAX_BULK} registros por importación"}), 400

    def key_of(r: dict):
        return tuple(str(r.get(k) or "").strip() for k in REC_KEYS)

    try:
        existentes = {
            key_of({**r, "fecha": str(r.get("fecha") or "")[:10]})
            for r in sb_get_all("/trabajos_externos", select=",".join(REC_KEYS), order="nro.asc")
        }
        nuevos, invalidos, duplicados = [], 0, 0
        uid = session.get("user_id")
        for raw in regs:
            body, err = clean_record(raw if isinstance(raw, dict) else {}, lenient=True)
            if err:
                invalidos += 1
                continue
            k = key_of(body)
            if k in existentes:
                duplicados += 1
                continue
            existentes.add(k)
            body["id"] = "r" + secrets.token_hex(8)
            body["user_id"] = uid
            nuevos.append(body)
        for i in range(0, len(nuevos), 200):
            sb_post("/trabajos_externos", nuevos[i : i + 200])
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"agregados": len(nuevos), "duplicados": duplicados, "invalidos": invalidos})


@app.route("/api/trabajos/<tid>", methods=["PUT"])
@login_required
def api_update(tid):
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    body, err = clean_record(request.get_json(silent=True) or {})
    if err:
        return jsonify({"error": err}), 400
    try:
        actual = get_trabajo(tid)
        if not actual:
            return jsonify({"error": "Registro no encontrado"}), 404
        if not can_edit_row(actual):
            return jsonify({"error": "Solo puedes editar los registros que tú creaste"}), 403
        body["actualizado"] = now_iso()
        rows = sb_patch("/trabajos_externos", body, id=f"eq.{tid}")
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    row = rows[0] if isinstance(rows, list) and rows else {**actual, **body}
    return jsonify(row_to_dict(row))


@app.route("/api/trabajos/<tid>", methods=["DELETE"])
@login_required
def api_delete(tid):
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    try:
        actual = get_trabajo(tid)
        if not actual:
            return jsonify({"error": "Registro no encontrado"}), 404
        if not can_edit_row(actual):
            return jsonify({"error": "Solo puedes eliminar los registros que tú creaste"}), 403
        sb_delete("/trabajos_externos", id=f"eq.{tid}")
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/next-nro")
@login_required
def api_next_nro():
    """Vista previa del siguiente ID (el definitivo lo asigna la BD al guardar)."""
    try:
        rows = sb_get("/trabajos_externos", select="nro", order="nro.desc", limit="1")
        return jsonify({"next": (int(rows[0]["nro"]) if rows else 0) + 1})
    except Exception as e:
        return jsonify({"next": 1, "warning": str(e)})


# ── Usuarios (solo admin) ───────────────────────────────────────────────────
@app.route("/api/users", methods=["GET"])
@login_required
def api_users_list():
    if not is_admin():
        return jsonify({"error": "Solo el administrador puede ver usuarios"}), 403
    try:
        rows = sb_get_all(
            "/usuarios2",
            select="id,usuario,nombre,rol,activo,created_at,password_changed_at",
            order="id.asc",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(rows)


@app.route("/api/users", methods=["POST"])
@login_required
def api_users_create():
    if not is_admin():
        return jsonify({"error": "Solo el administrador puede crear usuarios"}), 403
    data = request.get_json(silent=True) or {}
    usuario = str(data.get("usuario") or "").strip()
    password = str(data.get("password") or "").strip()
    nombre = str(data.get("nombre") or "").strip()
    rol = str(data.get("rol") or "usuario").strip().lower()
    if rol not in ROLES:
        rol = "usuario"
    if not usuario or not password or not nombre:
        return jsonify({"error": "usuario, password y nombre son obligatorios"}), 400
    err = validate_new_password(password, usuario)
    if err:
        return jsonify({"error": err}), 400
    try:
        if sb_get("/usuarios2", select="id", usuario=f"eq.{usuario}", limit="1"):
            return jsonify({"error": f"El usuario {usuario} ya existe"}), 409
        rows = sb_post(
            "/usuarios2",
            {
                "usuario": usuario,
                "password_hash": generate_password_hash(password, method=HASH_METHOD),
                "nombre": nombre,
                "rol": rol,
                "activo": True,
                "password_changed_at": now_iso(),
            },
        )
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    row = rows[0] if isinstance(rows, list) and rows else {}
    return jsonify({"ok": True, "id": row.get("id"), "usuario": usuario, "nombre": nombre}), 201


@app.route("/api/users/<int:uid>", methods=["PUT"])
@login_required
def api_users_update(uid):
    """Cambiar rol, nombre o activar/desactivar."""
    if not is_admin():
        return jsonify({"error": "Solo el administrador puede modificar usuarios"}), 403
    data = request.get_json(silent=True) or {}
    body = {}
    if "rol" in data:
        rol = str(data["rol"]).strip().lower()
        if rol not in ROLES:
            return jsonify({"error": "Rol no válido"}), 400
        body["rol"] = rol
    if "activo" in data:
        body["activo"] = bool(data["activo"])
    if "nombre" in data:
        nombre = str(data["nombre"]).strip()
        if not nombre:
            return jsonify({"error": "El nombre no puede quedar vacío"}), 400
        body["nombre"] = nombre
    if not body:
        return jsonify({"error": "Nada que actualizar"}), 400
    if uid == session.get("user_id") and ("rol" in body or body.get("activo") is False):
        return jsonify({"error": "No puedes cambiar tu propio rol ni desactivarte"}), 400
    try:
        rows = sb_patch("/usuarios2", body, id=f"eq.{uid}")
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    if not rows:
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify({"ok": True})


@app.route("/api/users/<int:uid>/password", methods=["PUT"])
@login_required
def api_users_reset_password(uid):
    """El admin restablece la contraseña de otro usuario."""
    if not is_admin():
        return jsonify({"error": "Solo el administrador puede restablecer contraseñas"}), 403
    nueva = str((request.get_json(silent=True) or {}).get("nueva") or "")
    try:
        rows = sb_get("/usuarios2", select="id,usuario", id=f"eq.{uid}", limit="1")
        if not rows:
            return jsonify({"error": "Usuario no encontrado"}), 404
        err = validate_new_password(nueva, rows[0]["usuario"])
        if err:
            return jsonify({"error": err}), 400
        sb_patch(
            "/usuarios2",
            {
                "password_hash": generate_password_hash(nueva, method=HASH_METHOD),
                "password_changed_at": now_iso(),
            },
            id=f"eq.{uid}",
        )
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/users/<int:uid>", methods=["DELETE"])
@login_required
def api_users_delete(uid):
    if not is_admin():
        return jsonify({"error": "Solo el administrador puede eliminar usuarios"}), 403
    if uid == session.get("user_id"):
        return jsonify({"error": "No puedes eliminarte a ti mismo"}), 400
    try:
        sb_delete("/usuarios2", id=f"eq.{uid}")
    except httpx.HTTPStatusError as e:
        return jsonify({"error": http_msg(e)}), 500
    return jsonify({"ok": True})


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5050"))
    print("=" * 56)
    print("  Registro de Trabajos Externos — CESOP Hogar")
    print(f"  http://{host}:{port}")
    print("  (desarrollo; en producción usa gunicorn/waitress, ver LEEME)")
    print("=" * 56)
    app.run(host=host, port=port, debug=False)
