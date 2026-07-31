# ADR 0001: monolito modular y tenant explícito

Estado: aceptado.

Cuadratura usa un proyecto Django y PostgreSQL propios. Todas las entidades operativas tienen FK obligatoria a `TaxpayerOrganization`; el acceso se decide por `OrganizationMembership`. No se comparte identidad ni esquema con Plataforma Elemental. Esta última podrá ser un cliente API externo solo después de diseñar autenticación, scopes e idempotencia.

