# ADR 0003: modelos preparados pero inactivos

Estado: propuesto, no implementado.

Los futuros modelos serán UUID y tenant-scoped cuando corresponda:

- `DigitalCertificateCredential`: organización, referencia opaca al secreto externo, huella, vigencia y estado; nunca bytes ni contraseña.
- `FolioAuthorization`: organización, tipo DTE, rango, vigencia, huella del CAF y referencia cifrada externa.
- `FolioReservation`: autorización, folio único, estado, operación, timestamps y lock/version.
- `ApiClient`: identidad técnica, digest de credencial, estado y scopes fijos.
- `ApiClientOrganization`: cliente, organización y capacidades explícitas.
- `IdempotencyRecord`: organización/cliente, clave, fingerprint, estado, respuesta estable y expiración.

No se agregan tablas hasta aprobar el contrato API o el spike SII; así se evita convertir hipótesis en esquema persistente.

