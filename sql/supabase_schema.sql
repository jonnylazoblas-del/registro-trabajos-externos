-- ============================================================
-- INSTALACIÓN NUEVA — Supabase -> SQL Editor -> New query -> Run
-- Registro de Trabajos Externos · CESOP Hogar
-- Tablas propias (NO toca public.usuarios).
-- Si ya tenías la versión anterior, NO uses este archivo:
-- usa migracion_paso1.sql / migracion_paso2.sql.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.usuarios2 (
  id                   bigserial PRIMARY KEY,
  usuario              text NOT NULL UNIQUE,
  password_hash        text NOT NULL,                 -- hash, nunca texto plano
  nombre               text NOT NULL,
  rol                  text NOT NULL DEFAULT 'usuario'
                       CHECK (rol IN ('admin','usuario','visor')),
  activo               boolean NOT NULL DEFAULT true,
  password_changed_at  timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now()
);

-- El ID de Atención sale de una secuencia: atómico, sin duplicados
CREATE SEQUENCE IF NOT EXISTS public.trabajos_nro_seq;

CREATE TABLE IF NOT EXISTS public.trabajos_externos (
  id           text PRIMARY KEY,
  nro          bigint NOT NULL UNIQUE DEFAULT nextval('public.trabajos_nro_seq'),
  fecha        date NOT NULL DEFAULT CURRENT_DATE,
  orden        text DEFAULT '',
  tipoorden    text DEFAULT '',
  codigo       text DEFAULT '',
  tiposerv     text DEFAULT 'Hogar',
  tipo         text DEFAULT '',
  area         text DEFAULT '',
  resultado    text DEFAULT '',
  accion       text DEFAULT '',
  red          text DEFAULT '',
  focal        text DEFAULT '',
  obs          text DEFAULT '',
  user_id      bigint REFERENCES public.usuarios2(id) ON DELETE SET NULL,
  creado       timestamptz NOT NULL DEFAULT now(),
  actualizado  timestamptz
);
ALTER SEQUENCE public.trabajos_nro_seq OWNED BY public.trabajos_externos.nro;

CREATE INDEX IF NOT EXISTS idx_trabajos_fecha ON public.trabajos_externos (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_trabajos_focal ON public.trabajos_externos (focal);
CREATE INDEX IF NOT EXISTS idx_trabajos_tipo  ON public.trabajos_externos (tipo);
CREATE INDEX IF NOT EXISTS idx_trabajos_user  ON public.trabajos_externos (user_id);

-- RLS activado SIN políticas: la API pública (anon/authenticated) no puede
-- leer nada. Solo el backend, con la secret key (service_role), tiene acceso.
ALTER TABLE public.usuarios2         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trabajos_externos ENABLE ROW LEVEL SECURITY;

-- Los usuarios se crean con:  python crear_usuarios.py --seed
SELECT 'OK usuarios2' AS status, count(*) AS filas FROM public.usuarios2;
SELECT 'OK trabajos_externos' AS status, count(*) AS filas FROM public.trabajos_externos;
