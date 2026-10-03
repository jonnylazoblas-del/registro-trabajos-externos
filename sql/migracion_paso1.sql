-- ============================================================
-- MIGRACIÓN desde la versión anterior (conserva tus datos)
-- PASO 1 de 3 — ejecutar en Supabase -> SQL Editor
-- Orden:  migracion_paso1.sql  ->  python migrar_passwords.py  ->  migracion_paso2.sql
-- ============================================================

-- Contraseñas con hash
ALTER TABLE public.usuarios2 ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE public.usuarios2 ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;
ALTER TABLE public.usuarios2 DROP CONSTRAINT IF EXISTS usuarios2_rol_check;
ALTER TABLE public.usuarios2 ADD CONSTRAINT usuarios2_rol_check
  CHECK (rol IN ('admin','usuario','visor'));

-- Correlativo atómico: secuencia que continúa donde ibas
CREATE SEQUENCE IF NOT EXISTS public.trabajos_nro_seq;
DO $$
DECLARE m bigint;
BEGIN
  SELECT GREATEST(
           COALESCE((SELECT max(nro) FROM public.trabajos_externos), 0),
           COALESCE((SELECT nro FROM public.trabajos_correlativo WHERE id = 1), 0)
         ) INTO m;
  IF m > 0 THEN
    PERFORM setval('public.trabajos_nro_seq', m, true);
  ELSE
    PERFORM setval('public.trabajos_nro_seq', 1, false);
  END IF;
END $$;
ALTER TABLE public.trabajos_externos
  ALTER COLUMN nro SET DEFAULT nextval('public.trabajos_nro_seq');
ALTER SEQUENCE public.trabajos_nro_seq OWNED BY public.trabajos_externos.nro;

-- Borrar un usuario ya no rompe: sus registros quedan sin dueño
ALTER TABLE public.trabajos_externos DROP CONSTRAINT IF EXISTS trabajos_externos_user_id_fkey;
ALTER TABLE public.trabajos_externos
  ADD CONSTRAINT trabajos_externos_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.usuarios2(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_trabajos_user ON public.trabajos_externos (user_id);

-- Quitar políticas permisivas (RLS queda activo sin políticas)
DROP POLICY IF EXISTS "auth usuarios2"            ON public.usuarios2;
DROP POLICY IF EXISTS "auth read write trabajos"  ON public.trabajos_externos;

SELECT 'Paso 1 OK' AS status, currval('public.trabajos_nro_seq') AS ultimo_nro;
