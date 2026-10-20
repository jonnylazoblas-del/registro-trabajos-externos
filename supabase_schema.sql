-- ============================================================
-- Ejecutar en Supabase → SQL Editor → New query → Run
-- Registro de Trabajos Externos · CESOP Hogar
-- Tablas propias (NO modifica public.usuarios)
-- ============================================================

-- Usuarios de ESTA app (separados de public.usuarios)
CREATE TABLE IF NOT EXISTS public.usuarios2 (
  id           bigserial PRIMARY KEY,
  usuario      text NOT NULL UNIQUE,
  password     text NOT NULL,
  nombre       text NOT NULL,
  rol          text NOT NULL DEFAULT 'usuario',  -- admin | usuario | visor
  activo       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Tabla principal de registros
CREATE TABLE IF NOT EXISTS public.trabajos_externos (
  id           text PRIMARY KEY,
  nro          bigint NOT NULL UNIQUE,
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
  user_id      bigint REFERENCES public.usuarios2(id),
  creado       timestamptz NOT NULL DEFAULT now(),
  actualizado  timestamptz
);

-- Correlativo del ID de Atención
CREATE TABLE IF NOT EXISTS public.trabajos_correlativo (
  id   int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  nro  bigint NOT NULL DEFAULT 0
);

INSERT INTO public.trabajos_correlativo (id, nro)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;

-- Usuarios iniciales (solo si no existen)
-- Roles: admin = todo | visor = solo ver y exportar Excel
INSERT INTO public.usuarios2 (usuario, password, nombre, rol)
VALUES
  ('JonnyECC',     'Jonny2030',      'Jonny Lazo',          'admin'),
  ('DianaECC',     'Dianacesop',     'Diana Julca',         'admin'),
  ('SebastianECC', 'Sebastiancesop', 'Sebastian Astudillo', 'admin'),
  ('RogerECC',     'Sebastiancesop', 'Roger Cumpa',         'admin'),
  ('AngelEntel',   'Angelentel',     'Angel Entel',         'visor'),
  ('ItaloEntel',   'Italoentel',     'Italo Entel',         'visor')
ON CONFLICT (usuario) DO NOTHING;

-- Índices
CREATE INDEX IF NOT EXISTS idx_trabajos_fecha ON public.trabajos_externos (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_trabajos_focal ON public.trabajos_externos (focal);
CREATE INDEX IF NOT EXISTS idx_trabajos_tipo  ON public.trabajos_externos (tipo);
CREATE INDEX IF NOT EXISTS idx_usuarios2_usuario ON public.usuarios2 (usuario);

-- RLS (service_role del backend bypasea RLS)
ALTER TABLE public.usuarios2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trabajos_externos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trabajos_correlativo ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "auth usuarios2" ON public.usuarios2;
CREATE POLICY "auth usuarios2" ON public.usuarios2
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "auth read write trabajos" ON public.trabajos_externos;
CREATE POLICY "auth read write trabajos" ON public.trabajos_externos
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "auth correlativo" ON public.trabajos_correlativo;
CREATE POLICY "auth correlativo" ON public.trabajos_correlativo
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- Verificación
SELECT 'OK usuarios2' AS status, usuario, nombre, rol FROM public.usuarios2 ORDER BY id;
SELECT 'OK trabajos_externos' AS status, count(*) AS filas FROM public.trabajos_externos;
SELECT 'OK correlativo' AS status, nro FROM public.trabajos_correlativo WHERE id = 1;

-- ============================================================
-- Bitácora de Feedback a Agentes
-- ============================================================

CREATE TABLE IF NOT EXISTS public.feedback_agentes (
  id              text PRIMARY KEY,
  nro             bigint NOT NULL UNIQUE,
  fecha           date NOT NULL DEFAULT CURRENT_DATE,
  hora            text DEFAULT '',
  supervisor      text DEFAULT '',
  agente          text DEFAULT '',
  id_agente       text DEFAULT '',
  area            text DEFAULT '',
  tipos           text DEFAULT '',
  detalle         text DEFAULT '',
  desc_evidencia  text DEFAULT '',
  evidencias      jsonb DEFAULT '[]'::jsonb,
  acciones        text DEFAULT '',
  fecha_seg       date,
  resultado_seg   text DEFAULT '',
  user_id         bigint REFERENCES public.usuarios2(id),
  creado          timestamptz NOT NULL DEFAULT now(),
  actualizado     timestamptz
);

CREATE TABLE IF NOT EXISTS public.feedback_correlativo (
  id   int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  nro  bigint NOT NULL DEFAULT 0
);

INSERT INTO public.feedback_correlativo (id, nro)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_feedback_fecha ON public.feedback_agentes (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_agente ON public.feedback_agentes (agente);

ALTER TABLE public.feedback_agentes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback_correlativo ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "auth feedback" ON public.feedback_agentes;
CREATE POLICY "auth feedback" ON public.feedback_agentes
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "auth feedback_correlativo" ON public.feedback_correlativo;
CREATE POLICY "auth feedback_correlativo" ON public.feedback_correlativo
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

SELECT 'OK feedback_agentes' AS status, count(*) AS filas FROM public.feedback_agentes;
SELECT 'OK feedback_correlativo' AS status, nro FROM public.feedback_correlativo WHERE id = 1;


-- Columna evidencias si la tabla ya existía sin ella
ALTER TABLE public.feedback_agentes
  ADD COLUMN IF NOT EXISTS evidencias jsonb DEFAULT '[]'::jsonb;

-- ============================================================
-- Storage: bucket público para evidencias de bitácora
-- (también se crea automáticamente desde la app al subir la 1.ª imagen)
-- En Supabase → Storage → New bucket → nombre: bitacora-evidencias → Public
-- O ejecuta vía API con service role. Políticas de ejemplo:
-- ============================================================
-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('bitacora-evidencias', 'bitacora-evidencias', true)
-- ON CONFLICT (id) DO NOTHING;
