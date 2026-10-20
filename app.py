#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
_user_site = Path.home() / ".local/lib/python3.12/site-packages"
if _user_site.exists() and str(_user_site) not in sys.path:
    sys.path.insert(0, str(_user_site))

    sys.path.insert(0, str(_user_site))

"""
Registro de Trabajos Externos — CESOP Hogar · Entel
Backend con login contra Supabase (tabla usuarios) y datos en trabajos_externos.
"""

import os
import secrets
from datetime import date
from functools import wraps

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

# ── Supabase config (override with env vars in production) ─────────────────
# Misma conexión de siempre. Solo usa env si trae valor real (no vacío).
SUPABASE_URL = (
    os.environ.get("SUPABASE_URL") or "https://hpzqnqlaubgrwciljjzd.supabase.co"
).strip().rstrip("/")
SUPABASE_SECRET = (
    os.environ.get("SUPABASE_SECRET") or "sb_secret_B2kzCP_hqYb_x8qS_sjD3w__Ft6Av28"
).strip()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
)

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


def sb_get(path: str, **params):
    r = _http.get(path, params=params)
    r.raise_for_status()
    return r.json()


def sb_post(path: str, body, extra_headers=None):
    headers = dict(extra_headers or {})
    r = _http.post(path, json=body, headers=headers)
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


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "No autenticado"}), 401
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


# Solo estos usuarios pueden entrar a la Bitácora de Feedback
BITACORA_ALLOWED_USERS = {
    "jonnyecc",
    "dianaecc",
    "sebastianecc",
    "rogerecc",
}


def current_user():
    if not session.get("user_id"):
        return None
    return {
        "id": session["user_id"],
        "username": session.get("username"),
        "nombre": session.get("nombre"),
        "rol": session.get("rol", "usuario"),
        "can_bitacora": can_access_bitacora(),
    }


def can_access_bitacora() -> bool:
    """Bitácora solo para Jonny, Diana, Sebastian y Roger."""
    u = (session.get("username") or "").strip().lower()
    return u in BITACORA_ALLOWED_USERS


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        try:
            rows = sb_get(
                "/usuarios2",
                select="id,usuario,password,nombre,rol,activo",
                usuario=f"eq.{username}",
                limit="1",
            )
        except Exception:
            rows = []
            error = "No se pudo conectar con la base de datos. Revisa Supabase."

        if not error:
            if rows and str(rows[0].get("password", "")) == password:
                u = rows[0]
                if u.get("activo") is False:
                    error = "Usuario desactivado. Contacta al administrador."
                else:
                    session.clear()
                    session.permanent = True
                    session["user_id"] = u["id"]
                    session["username"] = u["usuario"]
                    session["nombre"] = u.get("nombre") or u["usuario"]
                    session["rol"] = u.get("rol") or "usuario"
                    nxt = request.args.get("next") or url_for("index")
                    if not nxt.startswith("/"):
                        nxt = url_for("index")
                    return redirect(nxt)
            else:
                error = "Usuario o contraseña incorrectos."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user())


@app.route("/bitacora")
@login_required
def bitacora():
    if not can_access_bitacora():
        return redirect(url_for("index"))
    return render_template("bitacora.html", user=current_user())


def row_to_dict(r: dict) -> dict:
    fecha = r.get("fecha") or ""
    if isinstance(fecha, str) and "T" in fecha:
        fecha = fecha[:10]
    return {
        "id": r.get("id"),
        "nro": r.get("nro"),
        "fecha": fecha,
        "orden": r.get("orden") or "",
        "tipoorden": r.get("tipoorden") or "",
        "codigo": r.get("codigo") or "",
        "tiposerv": r.get("tiposerv") or "",
        "tipo": r.get("tipo") or "",
        "area": r.get("area") or "",
        "resultado": r.get("resultado") or "",
        "accion": r.get("accion") or "",
        "red": r.get("red") or "",
        "focal": r.get("focal") or "",
        "obs": r.get("obs") or "",
        "creado": r.get("creado"),
    }


def next_nro() -> int:
    rows = sb_get("/trabajos_correlativo", select="nro", id="eq.1", limit="1")
    if not rows:
        try:
            sb_post("/trabajos_correlativo", {"id": 1, "nro": 1})
            return 1
        except Exception as e:
            raise RuntimeError(
                "Falta la tabla trabajos_correlativo. Ejecuta supabase_schema.sql en el SQL Editor."
            ) from e
    current = int(rows[0]["nro"] or 0)
    new = current + 1
    sb_patch("/trabajos_correlativo", {"nro": new}, id="eq.1")
    return new


@app.route("/api/me")
@login_required
def api_me():
    return jsonify(current_user())


@app.route("/api/trabajos", methods=["GET"])
@login_required
def api_list():
    try:
        rows = sb_get(
            "/trabajos_externos",
            select="*",
            order="fecha.desc,nro.desc",
        )
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            return jsonify(
                {
                    "error": "Tabla trabajos_externos no existe. Ejecuta supabase_schema.sql en Supabase SQL Editor."
                }
            ), 500
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/trabajos", methods=["POST"])
@login_required
def api_create():
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    data = request.get_json(silent=True) or {}
    area = (data.get("area") or "").strip()
    focal = (data.get("focal") or "").strip()
    if not area:
        return jsonify({"error": "Área Solicitante es obligatoria"}), 400
    if not focal:
        return jsonify({"error": "Focal Responsable es obligatorio"}), 400

    try:
        nro = next_nro()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    tid = "r" + secrets.token_hex(8)
    fecha = (data.get("fecha") or date.today().isoformat())[:10]
    body = {
        "id": tid,
        "nro": nro,
        "fecha": fecha,
        "orden": (data.get("orden") or "").strip(),
        "tipoorden": (data.get("tipoorden") or "").strip(),
        "codigo": (data.get("codigo") or "").strip(),
        "tiposerv": (data.get("tiposerv") or "Hogar").strip(),
        "tipo": (data.get("tipo") or "Otro").strip(),
        "area": area,
        "resultado": (data.get("resultado") or "").strip(),
        "accion": (data.get("accion") or "").strip(),
        "red": (data.get("red") or "").strip(),
        "focal": focal,
        "obs": (data.get("obs") or "").strip(),
        "user_id": session.get("user_id"),
    }
    try:
        rows = sb_post("/trabajos_externos", body)
    except httpx.HTTPStatusError as e:
        msg = e.response.text[:300] if e.response is not None else str(e)
        return jsonify({"error": msg}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    row = rows[0] if isinstance(rows, list) and rows else body
    return jsonify(row_to_dict(row)), 201


@app.route("/api/trabajos/<tid>", methods=["PUT"])
@login_required
def api_update(tid):
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    data = request.get_json(silent=True) or {}
    area = (data.get("area") or "").strip()
    focal = (data.get("focal") or "").strip()
    if not area:
        return jsonify({"error": "Área Solicitante es obligatoria"}), 400
    if not focal:
        return jsonify({"error": "Focal Responsable es obligatorio"}), 400

    body = {
        "fecha": (data.get("fecha") or date.today().isoformat())[:10],
        "orden": (data.get("orden") or "").strip(),
        "tipoorden": (data.get("tipoorden") or "").strip(),
        "codigo": (data.get("codigo") or "").strip(),
        "tiposerv": (data.get("tiposerv") or "Hogar").strip(),
        "tipo": (data.get("tipo") or "Otro").strip(),
        "area": area,
        "resultado": (data.get("resultado") or "").strip(),
        "accion": (data.get("accion") or "").strip(),
        "red": (data.get("red") or "").strip(),
        "focal": focal,
        "obs": (data.get("obs") or "").strip(),
        "actualizado": date.today().isoformat(),
    }
    try:
        rows = sb_patch("/trabajos_externos", body, id=f"eq.{tid}")
    except httpx.HTTPStatusError as e:
        msg = e.response.text[:300] if e.response is not None else str(e)
        return jsonify({"error": msg}), 500

    if not rows:
        found = sb_get("/trabajos_externos", select="*", id=f"eq.{tid}", limit="1")
        if not found:
            return jsonify({"error": "Registro no encontrado"}), 404
        return jsonify(row_to_dict(found[0]))
    row = rows[0] if isinstance(rows, list) else rows
    return jsonify(row_to_dict(row))


@app.route("/api/trabajos/<tid>", methods=["DELETE"])
@login_required
def api_delete(tid):
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    try:
        sb_delete("/trabajos_externos", id=f"eq.{tid}")
    except httpx.HTTPStatusError as e:
        msg = e.response.text[:300] if e.response is not None else str(e)
        return jsonify({"error": msg}), 500
    return jsonify({"ok": True})


@app.route("/api/next-nro")
@login_required
def api_next_nro():
    try:
        rows = sb_get("/trabajos_correlativo", select="nro", id="eq.1", limit="1")
        nro = int(rows[0]["nro"]) if rows else 0
        return jsonify({"next": nro + 1})
    except Exception as e:
        return jsonify({"next": 1, "warning": str(e)})



# ── Bitácora de Feedback a Agentes ──────────────────────────────────────────

STORAGE_BUCKET = "bitacora-evidencias"
MAX_EVIDENCIA_BYTES = 8 * 1024 * 1024  # 8 MB por archivo
ALLOWED_EVIDENCIA_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
}


def _storage_headers(content_type: str | None = None) -> dict:
    h = {
        "apikey": SUPABASE_SECRET,
        "Authorization": f"Bearer {SUPABASE_SECRET}",
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


def ensure_storage_bucket() -> None:
    """Crea el bucket público de evidencias si aún no existe."""
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/storage/v1/bucket/{STORAGE_BUCKET}",
            headers=_storage_headers(),
            timeout=20.0,
        )
        if r.status_code == 200:
            return
    except Exception:
        pass
    try:
        httpx.post(
            f"{SUPABASE_URL}/storage/v1/bucket",
            headers=_storage_headers("application/json"),
            json={
                "id": STORAGE_BUCKET,
                "name": STORAGE_BUCKET,
                "public": True,
                "file_size_limit": MAX_EVIDENCIA_BYTES,
                "allowed_mime_types": list(ALLOWED_EVIDENCIA_MIME),
            },
            timeout=20.0,
        )
    except Exception:
        pass


def public_storage_url(path: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{path}"


def upload_evidencia_file(tid: str, file_storage) -> dict | None:
    """Sube un archivo a Supabase Storage y devuelve metadatos."""
    if not file_storage or not getattr(file_storage, "filename", None):
        return None
    raw_name = (file_storage.filename or "archivo").strip()
    mime = (file_storage.mimetype or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED_EVIDENCIA_MIME:
        # Algunos navegadores mandan application/octet-stream; permitir por extensión
        ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
        if ext not in ("jpg", "jpeg", "png", "webp", "gif", "pdf"):
            return None
        mime = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
            "pdf": "application/pdf",
        }.get(ext, "application/octet-stream")

    data = file_storage.read()
    if not data or len(data) > MAX_EVIDENCIA_BYTES:
        return None

    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw_name)[:80]
    path = f"{tid}/{secrets.token_hex(6)}_{safe}"
    ensure_storage_bucket()
    r = httpx.post(
        f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{path}",
        headers=_storage_headers(mime or "application/octet-stream"),
        content=data,
        timeout=60.0,
    )
    if r.status_code not in (200, 201):
        # reintento con upsert
        r = httpx.put(
            f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{path}",
            headers=_storage_headers(mime or "application/octet-stream"),
            content=data,
            timeout=60.0,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"No se pudo subir {raw_name}: {r.status_code} {r.text[:200]}")

    return {
        "path": path,
        "name": raw_name,
        "mime": mime,
        "size": len(data),
        "url": public_storage_url(path),
    }


def delete_storage_paths(paths: list) -> None:
    paths = [p for p in paths if p]
    if not paths:
        return
    try:
        httpx.request(
            "DELETE",
            f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}",
            headers=_storage_headers("application/json"),
            json={"prefixes": paths},
            timeout=30.0,
        )
    except Exception:
        pass


def parse_evidencias_field(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return []
        try:
            import json as _json

            parsed = _json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def feedback_to_dict(r: dict) -> dict:
    fecha = r.get("fecha") or ""
    if isinstance(fecha, str) and "T" in fecha:
        fecha = fecha[:10]
    fecha_seg = r.get("fecha_seg") or ""
    if isinstance(fecha_seg, str) and "T" in fecha_seg:
        fecha_seg = fecha_seg[:10]
    tipos = r.get("tipos") or ""
    if isinstance(tipos, list):
        tipos_list = tipos
    else:
        tipos_list = [t.strip() for t in str(tipos).split(",") if t.strip()]
    evidencias = parse_evidencias_field(r.get("evidencias"))
    # normalizar URLs por si el path quedó sin url
    for ev in evidencias:
        if isinstance(ev, dict) and ev.get("path") and not ev.get("url"):
            ev["url"] = public_storage_url(ev["path"])
    return {
        "id": r.get("id"),
        "nro": r.get("nro"),
        "fecha": fecha,
        "hora": r.get("hora") or "",
        "supervisor": r.get("supervisor") or "",
        "agente": r.get("agente") or "",
        "idAgente": r.get("id_agente") or "",
        "area": r.get("area") or "",
        "tipos": tipos_list,
        "detalle": r.get("detalle") or "",
        "descEvidencia": r.get("desc_evidencia") or "",
        "evidencias": evidencias,
        "acciones": r.get("acciones") or "",
        "fechaSeg": fecha_seg,
        "resultadoSeg": r.get("resultado_seg") or "",
        "creado": r.get("creado"),
    }


def _feedback_payload_from_request():
    """Lee JSON o multipart/form-data del request de feedback."""
    files = []
    if request.content_type and "multipart/form-data" in request.content_type:
        data = {k: request.form.get(k) for k in request.form.keys()}
        tipos_raw = request.form.getlist("tipos")
        if tipos_raw:
            data["tipos"] = tipos_raw
        elif data.get("tipos"):
            try:
                import json as _json

                data["tipos"] = _json.loads(data["tipos"])
            except Exception:
                data["tipos"] = [t.strip() for t in str(data["tipos"]).split(",") if t.strip()]
        files = request.files.getlist("files") or request.files.getlist("fotos") or []
    else:
        data = request.get_json(silent=True) or {}
    return data, files


def next_feedback_nro() -> int:
    rows = sb_get("/feedback_correlativo", select="nro", id="eq.1", limit="1")
    if not rows:
        try:
            sb_post("/feedback_correlativo", {"id": 1, "nro": 1})
            return 1
        except Exception as e:
            raise RuntimeError(
                "Falta la tabla feedback_correlativo. Ejecuta supabase_schema.sql en el SQL Editor."
            ) from e
    current = int(rows[0]["nro"] or 0)
    new = current + 1
    sb_patch("/feedback_correlativo", {"nro": new}, id="eq.1")
    return new


@app.route("/api/feedback", methods=["GET"])
@login_required
def api_feedback_list():
    if not can_access_bitacora():
        return jsonify({"error": "No tienes permiso para la bitácora de feedback"}), 403
    try:
        rows = sb_get(
            "/feedback_agentes",
            select="*",
            order="fecha.desc,nro.desc",
        )
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            return jsonify(
                {
                    "error": "Tabla feedback_agentes no existe. Ejecuta supabase_schema.sql en Supabase SQL Editor."
                }
            ), 500
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify([feedback_to_dict(r) for r in rows])


@app.route("/api/feedback", methods=["POST"])
@login_required
def api_feedback_create():
    if not can_access_bitacora():
        return jsonify({"error": "No tienes permiso para la bitácora de feedback"}), 403
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    data, files = _feedback_payload_from_request()
    agente = (data.get("agente") or "").strip()
    detalle = (data.get("detalle") or "").strip()
    if not agente and not detalle:
        return jsonify({"error": "Completa al menos el nombre del agente o el detalle"}), 400

    try:
        nro = next_feedback_nro()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    tipos = data.get("tipos") or []
    if isinstance(tipos, str):
        tipos_str = tipos
    else:
        tipos_str = ",".join(str(t).strip() for t in tipos if str(t).strip())

    tid = "fb" + secrets.token_hex(8)
    fecha = (data.get("fecha") or date.today().isoformat())[:10]
    fecha_seg = (data.get("fechaSeg") or "").strip()[:10] or None

    evidencias = []
    try:
        for f in files:
            meta = upload_evidencia_file(tid, f)
            if meta:
                evidencias.append(meta)
    except Exception as e:
        return jsonify({"error": f"Error al subir evidencias: {e}"}), 500

    body = {
        "id": tid,
        "nro": nro,
        "fecha": fecha,
        "hora": (data.get("hora") or "").strip(),
        "supervisor": (data.get("supervisor") or "").strip() or (session.get("nombre") or ""),
        "agente": agente,
        "id_agente": (data.get("idAgente") or "").strip(),
        "area": (data.get("area") or "").strip(),
        "tipos": tipos_str,
        "detalle": detalle,
        "desc_evidencia": (data.get("descEvidencia") or "").strip(),
        "evidencias": evidencias,
        "acciones": (data.get("acciones") or "").strip(),
        "fecha_seg": fecha_seg,
        "resultado_seg": (data.get("resultadoSeg") or "").strip(),
        "user_id": session.get("user_id"),
    }
    try:
        rows = sb_post("/feedback_agentes", body)
    except httpx.HTTPStatusError as e:
        msg = e.response.text[:400] if e.response is not None else str(e)
        if evidencias:
            delete_storage_paths([ev["path"] for ev in evidencias])
        # Si falla por columna evidencias inexistente, reintentar sin ella
        if "evidencias" in msg.lower() or "column" in msg.lower():
            body.pop("evidencias", None)
            try:
                rows = sb_post("/feedback_agentes", body)
                return jsonify({
                    **feedback_to_dict(rows[0] if isinstance(rows, list) and rows else body),
                    "warning": "Ejecuta el SQL de evidencias en Supabase para guardar URLs de imágenes en la tabla. Archivos subidos: "
                    + str(len(evidencias)),
                    "evidencias": evidencias,
                }), 201
            except Exception as e2:
                return jsonify({"error": str(e2)}), 500
        return jsonify({"error": msg}), 500
    except Exception as e:
        if evidencias:
            delete_storage_paths([ev["path"] for ev in evidencias])
        return jsonify({"error": str(e)}), 500

    row = rows[0] if isinstance(rows, list) and rows else body
    out = feedback_to_dict(row)
    if not out.get("evidencias") and evidencias:
        out["evidencias"] = evidencias
    return jsonify(out), 201


@app.route("/api/feedback/<tid>", methods=["PUT"])
@login_required
def api_feedback_update(tid):
    if not can_access_bitacora():
        return jsonify({"error": "No tienes permiso para la bitácora de feedback"}), 403
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    data, files = _feedback_payload_from_request()
    agente = (data.get("agente") or "").strip()
    detalle = (data.get("detalle") or "").strip()
    if not agente and not detalle:
        return jsonify({"error": "Completa al menos el nombre del agente o el detalle"}), 400

    tipos = data.get("tipos") or []
    if isinstance(tipos, str):
        tipos_str = tipos
    else:
        tipos_str = ",".join(str(t).strip() for t in tipos if str(t).strip())

    fecha_seg = (data.get("fechaSeg") or "").strip()[:10] or None
    body = {
        "fecha": (data.get("fecha") or date.today().isoformat())[:10],
        "hora": (data.get("hora") or "").strip(),
        "supervisor": (data.get("supervisor") or "").strip(),
        "agente": agente,
        "id_agente": (data.get("idAgente") or "").strip(),
        "area": (data.get("area") or "").strip(),
        "tipos": tipos_str,
        "detalle": detalle,
        "desc_evidencia": (data.get("descEvidencia") or "").strip(),
        "acciones": (data.get("acciones") or "").strip(),
        "fecha_seg": fecha_seg,
        "resultado_seg": (data.get("resultadoSeg") or "").strip(),
        "actualizado": date.today().isoformat(),
    }

    # evidencias existentes + nuevas subidas
    existing = parse_evidencias_field(data.get("evidenciasExistentes") or data.get("evidencias"))
    new_ev = []
    try:
        for f in files:
            meta = upload_evidencia_file(tid, f)
            if meta:
                new_ev.append(meta)
    except Exception as e:
        return jsonify({"error": f"Error al subir evidencias: {e}"}), 500
    if existing or new_ev:
        body["evidencias"] = list(existing) + new_ev

    try:
        rows = sb_patch("/feedback_agentes", body, id=f"eq.{tid}")
    except httpx.HTTPStatusError as e:
        msg = e.response.text[:300] if e.response is not None else str(e)
        if "evidencias" in msg.lower() and "evidencias" in body:
            body.pop("evidencias", None)
            try:
                rows = sb_patch("/feedback_agentes", body, id=f"eq.{tid}")
            except Exception as e2:
                return jsonify({"error": str(e2)}), 500
        else:
            return jsonify({"error": msg}), 500

    if not rows:
        found = sb_get("/feedback_agentes", select="*", id=f"eq.{tid}", limit="1")
        if not found:
            return jsonify({"error": "Registro no encontrado"}), 404
        out = feedback_to_dict(found[0])
        if new_ev and not out.get("evidencias"):
            out["evidencias"] = list(existing) + new_ev
        return jsonify(out)
    row = rows[0] if isinstance(rows, list) else rows
    return jsonify(feedback_to_dict(row))


@app.route("/api/feedback/<tid>", methods=["DELETE"])
@login_required
def api_feedback_delete(tid):
    if not can_access_bitacora():
        return jsonify({"error": "No tienes permiso para la bitácora de feedback"}), 403
    if not can_write():
        return jsonify({"error": "Tu perfil solo permite ver y exportar"}), 403
    # borrar archivos del storage antes del registro
    try:
        found = sb_get("/feedback_agentes", select="evidencias", id=f"eq.{tid}", limit="1")
        if found:
            paths = [ev.get("path") for ev in parse_evidencias_field(found[0].get("evidencias")) if isinstance(ev, dict)]
            # también limpia la carpeta del registro
            delete_storage_paths(paths + [f"{tid}/"])
    except Exception:
        pass
    try:
        sb_delete("/feedback_agentes", id=f"eq.{tid}")
    except httpx.HTTPStatusError as e:
        msg = e.response.text[:300] if e.response is not None else str(e)
        return jsonify({"error": msg}), 500
    return jsonify({"ok": True})


@app.route("/api/feedback-next-nro")
@login_required
def api_feedback_next_nro():
    if not can_access_bitacora():
        return jsonify({"error": "No tienes permiso para la bitácora de feedback"}), 403
    try:
        rows = sb_get("/feedback_correlativo", select="nro", id="eq.1", limit="1")
        nro = int(rows[0]["nro"]) if rows else 0
        return jsonify({"next": nro + 1})
    except Exception as e:
        return jsonify({"next": 1, "warning": str(e)})


# ── API usuarios (crear / listar) ───────────────────────────────────────────

def is_admin() -> bool:
    """Admin si el rol de sesión es admin."""
    return session.get("rol") == "admin"


def can_write() -> bool:
    """Admin y usuario pueden crear/editar/eliminar. Visor solo lectura+export."""
    return session.get("rol") in ("admin", "usuario")


@app.route("/api/users", methods=["GET"])
@login_required
def api_users_list():
    if not is_admin():
        return jsonify({"error": "Solo el administrador puede ver usuarios"}), 403
    try:
        rows = sb_get(
            "/usuarios2",
            select="id,usuario,nombre,rol,activo,created_at",
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
    if rol not in ("admin", "usuario", "visor"):
        rol = "usuario"
    if not usuario or not password or not nombre:
        return jsonify({"error": "usuario, password y nombre son obligatorios"}), 400
    try:
        exists = sb_get("/usuarios2", select="id", usuario=f"eq.{usuario}", limit="1")
        if exists:
            return jsonify({"error": f"El usuario {usuario} ya existe"}), 409
        rows = sb_post(
            "/usuarios2",
            {"usuario": usuario, "password": password, "nombre": nombre, "rol": rol, "activo": True},
        )
    except httpx.HTTPStatusError as e:
        msg = e.response.text[:300] if e.response is not None else str(e)
        return jsonify({"error": msg}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    row = rows[0] if isinstance(rows, list) and rows else {}
    return jsonify(
        {
            "ok": True,
            "id": row.get("id"),
            "usuario": row.get("usuario", usuario),
            "nombre": row.get("nombre", nombre),
        }
    ), 201


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
        msg = e.response.text[:300] if e.response is not None else str(e)
        return jsonify({"error": msg}), 500
    return jsonify({"ok": True})



if __name__ == "__main__":
    print("=" * 56)
    print("  Registro de Trabajos Externos — CESOP Hogar")
    print(f"  Supabase: {SUPABASE_URL}")
    print("  http://127.0.0.1:5050")
    print("  Login con usuarios de la tabla 'usuarios2' de Supabase")
    print("=" * 56)
    app.run(host="0.0.0.0", port=5050, debug=False)
