from django.db import migrations

SQL = r"""
CREATE OR REPLACE FUNCTION cuadratura_confirmed_batch_no_delete() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'COMMITTED' THEN
    RAISE EXCEPTION 'Los lotes de importación confirmados no pueden eliminarse';
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cuadratura_confirmed_row_no_delete() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'IMPORTED' OR EXISTS (
    SELECT 1 FROM imports_importbatch batch
    WHERE batch.id = OLD.batch_id AND batch.status = 'COMMITTED'
  ) THEN
    RAISE EXCEPTION 'Las filas de importación confirmadas no pueden eliminarse';
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER confirmed_batch_no_delete
BEFORE DELETE ON imports_importbatch
FOR EACH ROW EXECUTE FUNCTION cuadratura_confirmed_batch_no_delete();

CREATE TRIGGER confirmed_row_no_delete
BEFORE DELETE ON imports_importrow
FOR EACH ROW EXECUTE FUNCTION cuadratura_confirmed_row_no_delete();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS confirmed_row_no_delete ON imports_importrow;
DROP TRIGGER IF EXISTS confirmed_batch_no_delete ON imports_importbatch;
DROP FUNCTION IF EXISTS cuadratura_confirmed_row_no_delete();
DROP FUNCTION IF EXISTS cuadratura_confirmed_batch_no_delete();
"""


class Migration(migrations.Migration):
    dependencies = [("imports", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE_SQL)]

