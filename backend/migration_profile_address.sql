-- Execute no SQL Editor do Supabase para adicionar o endereço de perfil.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS address VARCHAR(300) NOT NULL DEFAULT '';

COMMIT;
