from django.db import migrations

SQL = r"""
CREATE OR REPLACE FUNCTION cuadratura_reject_delete() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'Los registros financieros y de auditoría no pueden eliminarse'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_auditevent FOR EACH ROW EXECUTE FUNCTION cuadratura_reject_delete();
CREATE TRIGGER sale_no_delete BEFORE DELETE ON sales_sale FOR EACH ROW EXECUTE FUNCTION cuadratura_reject_delete();
CREATE TRIGGER payment_no_delete BEFORE DELETE ON payments_payment FOR EACH ROW EXECUTE FUNCTION cuadratura_reject_delete();
CREATE TRIGGER receipt_no_delete BEFORE DELETE ON documents_electronicreceipt FOR EACH ROW EXECUTE FUNCTION cuadratura_reject_delete();
CREATE TRIGGER close_no_delete BEFORE DELETE ON reports_monthlyclose FOR EACH ROW EXECUTE FUNCTION cuadratura_reject_delete();

CREATE OR REPLACE FUNCTION cuadratura_accepted_receipt_immutable() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'ACCEPTED' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'Una boleta aceptada es inmutable; use un flujo de corrección o anulación';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER accepted_receipt_immutable BEFORE UPDATE ON documents_electronicreceipt FOR EACH ROW EXECUTE FUNCTION cuadratura_accepted_receipt_immutable();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS accepted_receipt_immutable ON documents_electronicreceipt;
DROP TRIGGER IF EXISTS close_no_delete ON reports_monthlyclose;
DROP TRIGGER IF EXISTS receipt_no_delete ON documents_electronicreceipt;
DROP TRIGGER IF EXISTS payment_no_delete ON payments_payment;
DROP TRIGGER IF EXISTS sale_no_delete ON sales_sale;
DROP TRIGGER IF EXISTS audit_no_delete ON audit_auditevent;
DROP FUNCTION IF EXISTS cuadratura_accepted_receipt_immutable();
DROP FUNCTION IF EXISTS cuadratura_reject_delete();
"""

class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"), ("documents", "0001_initial"),
        ("payments", "0002_payment_payment_amount_positive"),
        ("reports", "0001_initial"), ("sales", "0001_initial"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE_SQL)]

