# ADR 0002: integración SII cerrada por defecto

Estado: aceptado.

`SiiGateway` define `submit` y `query`. `DisabledSiiGateway` es el único adaptador permitido fuera de pruebas y levanta un error fijo. `FakeSiiGateway` se inyecta exclusivamente en tests. `SiiProfile.productive_issuance_enabled` es no editable y siempre falso en este corte. No hay credenciales, XML, CAF, folios ni red SII.

## Checklist exacto para comenzar el spike en certificación

- [ ] Obtener autorización formal escrita para trabajar solo en certificación y designar responsable tributario.
- [ ] Registrar versión, fecha, URL y hash de cada XSD oficial SII; conservar artefactos inmutables.
- [ ] Confirmar DTE 39/41 habilitados por organización y casos oficiales de certificación.
- [ ] Aprobar modelo de custodia: certificado/llave en secret manager o HSM; contraseña separada; llave maestra fuera de PostgreSQL; redacción de logs probada.
- [ ] Activar los diseños `DigitalCertificateCredential`, `FolioAuthorization` y `FolioReservation` mediante ADR y migración revisada.
- [ ] Implementar y validar XML de boleta contra XSD versionado.
- [ ] Implementar timbre electrónico con CAF y verificar rango, RUT, tipo DTE, expiración y firma del CAF.
- [ ] Implementar firma XML con certificado vigente y cadena validada; nunca exportar llave privada.
- [ ] Implementar semilla y token específicos del servicio de boletas en certificación, con reloj sincronizado y renovación controlada.
- [ ] Implementar envío persistiendo fingerprint, intento y `track_id` antes de habilitar una nueva acción.
- [ ] Implementar consulta de envío y consulta del documento con mapeo explícito a estados internos.
- [ ] Ante timeout, persistir `UNCERTAIN`, bloquear reemisión y ejecutar recuperación por consulta/fingerprint.
- [ ] Reservar folios atómicamente con bloqueo PostgreSQL, unicidad, rango CAF y pruebas concurrentes.
- [ ] Generar representación imprimible/virtual desde datos aceptados y validar requisitos visuales/tributarios.
- [ ] Ejecutar casos felices, rechazo, timeout, reintento, token expirado, certificado expirado, CAF agotado y concurrencia en certificación.
- [ ] Obtener aprobación de seguridad, contadora y responsable tributario; adjuntar evidencias de certificación.
- [ ] Mantener producción deshabilitada hasta disponer de certificación, CAF, certificado vigente y autorización formal; el paso a producción requiere otro ADR y control de doble aprobación.

