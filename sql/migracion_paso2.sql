-- ============================================================
-- PASO 3 de 3 — ejecutar DESPUÉS de python migrar_passwords.py
-- Elimina las contraseñas en texto plano y la tabla del correlativo viejo.
-- ============================================================

-- Verifica primero: debe devolver 0 filas
SELECT usuario FROM public.usuarios2 WHERE password_hash IS NULL;

ALTER TABLE public.usuarios2 ALTER COLUMN password_hash SET NOT NULL;
ALTER TABLE public.usuarios2 DROP COLUMN IF EXISTS password;
DROP TABLE IF EXISTS public.trabajos_correlativo;

SELECT 'Migración completa' AS status;
