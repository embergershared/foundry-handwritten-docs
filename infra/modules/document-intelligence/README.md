# Document Intelligence

Single-service `FormRecognizer` S0 account for Entra-authenticated layout recognition.
Uses the shared `di` global naming rule. Composition is opt-in; catalog membership
does not deploy this module.

`name`, `location` and `tags` follow the common module contract. Public access is
disabled by default. `allowedClientIpv4` permits exactly one approved workstation
address when public access is explicitly enabled; empty means deny all clients.
There is no trusted-service bypass or key authentication. Private endpoints are not
implemented by this module.

`operatorPrincipalIds` receive Cognitive Services User on this account only when
`enableRoleAssignments` is true. `logAnalyticsWorkspaceId` enables only `AllMetrics`,
never document/request/response logs. Outputs are `id`, `name` and `endpoint`; no keys.

See [the handwriting deployment guide](../../../docs/handwriting-azure.md).
