# Deployment plan

This is the project's deployment contract. `azure-prepare` fills it in,
`azure-validate` records evidence against it, and `azure-deploy` changes Azure
only after the approval below is recorded. Keep it aligned with `README.md`,
`docs/`, `azure.yaml`, the hooks and the Bicep.

Status: **Provisioned; management verification passed. Data-plane access blocked:
authenticated read-only requests return HTTP 403 (network/firewall). Not ready for a live pilot.**

## Preparation scope

Prepare the existing azd/Bicep starter for the local handwriting PoC: minimal Foundry
account/project and a pinned vision deployment, Document Intelligence, Entra-only
authentication, scoped RBAC, endpoint outputs, and existing monitoring/naming/preflight
conventions. Preserve the completed offline application. No app hosting, queues or
document storage are needed for this local workflow.

The user supplied a target subscription privately. Keep its actual identifier and
environment-specific values only in ignored local state, never in this public plan.
The user confirmed East US 2 and restricted public connectivity. Present this
concrete plan for approval before generating infrastructure.
The user subsequently requested deployment of the required resources together in one
dedicated environment resource group. This authorizes the scoped non-destructive
deployment after target decisions, plan approval and required validation; it does not
authorize document upload or unrelated services. Subsequent explicit network choices
are recorded below.

## Target

| Item | Value |
|---|---|
| azd environment | `handwriting-poc` (new, isolated environment) |
| Recipe | AZD (`recipe.type: azd`), existing modular Bicep |
| Tenant | Target subscription's tenant; exact ID/code remain in ignored local catalog/state |
| Subscription | User-supplied enabled subscription; exact ID and derived code remain local |
| Region | `eastus2` (`use2`), user selected |
| Deployment profile | `core`; preserve all other profile defaults |
| Feature overrides | Explicit `aiFoundry` and `documentIntelligence` opt-ins |
| Catalog modules | Existing `monitoring`, existing `ai-foundry`, new `document-intelligence` |
| Resource scope | One new dedicated environment RG, all workload resources inside it |
| Client | Existing workstation/local Python CLI; no hosted application |

### Resource and configuration inventory

| Component | Proposed configuration |
|---|---|
| Resource group | Existing subscription-scope naming/tags; fail before changes if the proposed group is not new |
| Foundry account/project | Reuse existing AIServices S0 module and project; system-assigned identities; keys disabled |
| Vision deployment | `handwriting-vision`: `gpt-4.1`, pinned `2025-04-14`, regional `Standard`, capacity 10 (10,000 TPM), no automatic upgrade |
| Document Intelligence | New single-service `FormRecognizer` S0 account; custom subdomain for Entra authentication; GA API `2024-11-30` used by the application |
| AI service firewalls | Public network enabled, ACL default Deny, exactly one approved workstation IPv4; Foundry bypass None, DI has no supported trusted-service bypass |
| Operator access | OpenAI User at Foundry account; Azure AI User at project; Cognitive Services User at DI account; explicit current operator only |
| Monitoring | Existing Log Analytics/Application Insights core module, 30-day retention and 1-GB/day ingestion cap; metrics-only AI diagnostics |
| Outputs | DI endpoint, OpenAI endpoint, Foundry project endpoint, deployment name/model/version; no keys, credentials or connection strings |
| Excluded | Storage, queues, hosting, Search, Key Vault, Bastion, VMs, NAT and private endpoint infrastructure |

Names use the shared naming functions and catalog. Add the CAF document-intelligence
abbreviation/name rule to the shared catalog, not a second naming algorithm. Keep
actual names/endpoints/IDs/IPs only in ignored azd state and private execution evidence.
Any local tenant-catalog addition is ignored and must preserve existing entries.

### Implementation steps

1. Extend the existing Foundry module with deny-by-default ACLs, narrowly scoped
   operator roles and metrics-only diagnostics; add a matching DI catalog module.
2. Wire both as default-off feature overrides in subscription composition, azd
   parameters, hooks and preflight; preserve core/private/full behavior without opt-in.
3. Validate IPv4, required operators, provider registration, selected regional model
   version/SKU/capacity and service-specific quota before provisioning. Reject empty
   or unrestricted public allowlists. Keep target-bearing output in private local logs.
4. Update docs/catalog/generated tables using the existing generators and add synthetic
   Bicep/preflight regression tests. Run local application and infrastructure checks.
5. Configure the isolated azd environment using explicit target/region and ignored
   state. Run package, ARM validation/policy/permission checks and azd what-if preview.
   Stop if resources outside the dedicated scope would change.
6. Invoke azure-validate, then azure-deploy. Provision only the reviewed environment.
   Verify actual resource states, model readiness, ACLs, auth, role assignments and
   authenticated read-only endpoints without inference or document submission.

## Decisions

Record each decision with its date, who approved it, and the alternatives and
consequences considered. A later decision supersedes an earlier one explicitly;
do not rewrite history.

- 2026-10-29, user: deploy the required resources together in one dedicated RG,
  using the existing azd/Bicep starter. This supersedes preparation-only scope;
  document upload remains unauthorized.
- 2026-10-29, user: East US 2 rather than West Europe or an automatically selected region.
- 2026-10-29, user: start with public endpoints, restricted to this workstation's
  current public IPv4. This supersedes the initially preferred private-access option
  for these two AI services only; it is not permission for unrestricted access.
- Proposed: regional Standard rather than GlobalStandard/DataZoneStandard to keep
  inference processing regional; pay-per-token rather than reserved provisioned units.
- Proposed: GPT-4.1 provides a pinned vision/structured-output baseline compatible
  with the existing adapter. The live catalog marks it Legacy and lists inference
  retirement on 2027-04-14. This is a short-lived PoC, not a production model commitment;
  migration/calibration is required before retirement and no accuracy is claimed.

## Public exceptions and risks

- Foundry and DI: explicitly approved workstation-only public endpoints with Entra
  tokens, disabled key authentication and default-deny IPv4 firewalls. Discover the
  current egress IP without echoing it and store it only in local azd state. An IP
  change requires an explicit local allowlist update; never fall back to all networks.
- Monitoring: preserve starter core-profile public Azure Monitor endpoints with Entra
  authentication/resource permissions; Azure Monitor does not offer these AI-service
  IP ACLs. Enable AI metrics only, not request/response, prompt, completion or document
  content logging. No documents, images or literal recognized text in telemetry.
- Costs: S0 DI is metered by processed pages and the Standard model by tokens; no
  reserved throughput or always-on compute. No data calls are authorized in this
  assignment. Monitoring ingestion may still incur charges; its cap is not a hard
  spending limit. Exact regional prices and any subscription offer must be checked
  before a later data pilot; do not claim a zero-cost deployment.
- Quota: Cognitive Services reports 1,000 regional GPT-4.1 units available (0 used),
  above the proposed 10; AIServices account count is 1/100 and total accounts 1/200.
  Model advertising and quota are not a capacity reservation; deployment can still fail.
- Generic `az quota list` is blocked because Microsoft.Quota is unregistered. Do not
  register an unnecessary provider. Use the actual Cognitive Services model/usage APIs
  and record this limitation rather than claiming generic quota validation passed.
- Permissions/policy, unique names, DI account availability, diagnostic categories and
  read-only data-plane verification remain to be checked. Stop on failure; no silent
  alternate model, region, exposure or privileged grant.
- Recovery: rerun the same idempotent Bicep for incomplete non-destructive provisioning.
  A destructive teardown, purge or resource replacement requires separate consent.
  Preserve the unchanged local application and private source documents throughout.
- Independent plan review, 2026-10-29: no blocking findings. Dispositions: implement
  separate account/project role scopes and assert them in compiled-template tests;
  assert logs never echo resolved identifiers/IPs; route only `AllMetrics` to this
  same dedicated core workspace; verify IPv4 connectivity without weakening ACLs.
  IPv6/proxy mismatch must fail closed. Reassess GPT-4.1 by 2027-03-01, before retirement.
  Budget alerts are outside this minimal no-inference deployment; no spending cap
  or cost ceiling is implied by quota or the monitoring ingestion cap.

## Validation checklist

All checks must pass before a deployment. A passing PR or offline test run does
not waive any of them.

- [x] Verify the AZD installation and the `azure.yaml` schema.
- [x] Confirm the environment, tenant, subscription, region and scope.
- [x] Verify authentication, providers, quota, licensing and permissions.
- [x] Run `./tests/run-tests.ps1`.
- [x] Run preflight and `azd provision --preview -e handwriting-poc`.
- [x] Repeat Bicep build/lint and validate packaging with `azd package`.
- [x] Review effective Azure policy and static RBAC.
- [x] Assert account/project roles have distinct intended scopes.
- [x] Check captured logs/outputs for identifier/IP leakage before public reporting.
- [ ] Verify `AllMetrics` only and IPv4 endpoint access with no inference/documents.
- [ ] Record the environment-specific evidence below.

### All validation checks pass

- [x] 1. AZD installation.
- [x] 2. Schema/configuration validation through azd packaging.
- [x] 3. Isolated environment setup.
- [x] 4. AZD authentication check.
- [x] 5. Explicit subscription/location and new dedicated group check.
- [x] 6. Aspire pre-provision checks: not applicable (no Aspire application).
- [x] 7. Target-specific provision preview.
- [x] 8. Build/full infrastructure verification.
- [x] 9. Docker context: not applicable (no hosted services or Dockerfiles).
- [x] 10. Package validation.
- [x] 11. Azure policy validation.
- [x] 12. Aspire post-provision checks: not applicable.

## Approval

- 2026-10-29: user authorized scoped deployment in the supplied subscription, one
  dedicated RG, East US 2, workstation-IPv4-restricted public AI endpoints.
- 2026-10-29: user selected "Approve this plan (Recommended)" for the concrete
  inventory/model/implementation and subsequent validated scoped deployment.

## Evidence

Record each validation or deployment run: the date, the environment, the
commands run, and the result. Never record secrets or `.env` contents.

- 2026-10-29: read-only discovery confirmed target Enabled, AzureCloud and
  Microsoft.CognitiveServices Registered. No subscription context changed.
- 2026-10-29: `az cognitiveservices model list --location eastus2` advertised
  AIServices GPT-4.1 `2025-04-14` with Standard SKU; its nested SKU metadata supplies
  1,000 tokens/unit/minute and the retirement noted above.
- 2026-10-29: `az cognitiveservices usage list --location eastus2` supplied actual
  regional model/account usage above. `az quota list` returned
  `MissingRegistrationForResourceProvider` for Microsoft.Quota; no registration attempted.
- 2026-10-29: Foundry dependency script confirmed azd and its existing Foundry
  extension are ready; nothing installed. No provisioning or document processing.
- 2026-10-29: six new targeted infrastructure tests and all 60 Python tests passed.
  The first expanded full suite had 104 passes and five adoption-hook failures:
  the conventions payload did not yet copy the new preflight helper. Added that
  dependency to the existing payload; verification of the fix remains pending.
- 2026-10-29: isolated local `handwriting-poc` environment configured with explicit
  approved target/region, operator and one IPv4. Proposed dedicated RG does not exist.
  Target values and raw logs are ignored under `.azure/` and `artifacts/azure-private/`.
- 2026-10-29: target-specific preflight and `azd package --no-prompt --environment
  handwriting-poc` passed. DI S0 is advertised with no regional restrictions.
- 2026-10-29: effective subscription permissions cover the nine required management
  writes, including role assignments. Three policy assignments were captured privately;
  policy enforcement/target what-if remain pending. No providers registered or cloud
  resources created.
- 2026-10-29: first read-only preview failed with `NetworkAclsBypassNotSupported`:
  FormRecognizer rejects the `networkAcls.bypass` property even when None. Omit
  that unsupported DI property, retain default Deny and the one-IP allowlist,
  assert its absence in regression tests, then repeat preview. This is not a
  trusted-service exception or firewall relaxation; no resources were provisioned.
- 2026-10-29: corrected `azd provision --preview --environment handwriting-poc
  --no-prompt` passed. Seven primary creates: one RG, two AI accounts, one project,
  one model deployment, Application Insights and Log Analytics. No modifications or
  deletions of existing workload resources. RBAC/diagnostics are nested resource extensions.
- 2026-10-29: `azd auth login --check-status --no-prompt` and official MCP
  `validate_azure_yaml` passed. Bicep build/lint and offline wheel build passed.
  The adoption regression subset passed 36/36 after fixing the payload dependency.
- 2026-10-29: reviewed all 11 members of the three inherited built-in policy
  initiatives. Their DeployIfNotExists rules target SQL/Synapse/database/Arc
  resources, not the proposed AI/monitoring types. Corrected target preview passed
  provider validation; no policy bypass, assignment change or provider registration.

## Role Assignment Verification

- Status: statically verified, including compiled-template regression tests.
- Current explicitly configured operator receives account-scoped Cognitive Services
  OpenAI User, project-scoped Azure AI User and DI-account Cognitive Services User.
- No subscription/RG data-role grants, owner grants or wildcard custom roles added.
- Foundry account/project system identities are platform identities with no requested
  downstream data operations in this local-client PoC; no speculative grants added.
- Effective deployer permissions include all nine required management writes.
- Live provisioned-role and data-plane checks remain post-deployment work.

## 7. Validation Proof

| Check/command | Result |
|---|---|
| `./tests/run-tests.ps1 -Name handwriting-infra` | Passed 6/6 synthetic access/quota/profile/compiled-RBAC tests |
| `./tests/run-tests.ps1 -Name tooling` | Passed 36/36, including adopted preflight helper closure |
| `./tests/run-tests.ps1` | Final run passed 109/109; three bash/jq-dependent subprocess checks still skip when tools are absent |
| `./scripts/build-catalog.ps1 -Check` | Passed |
| `./scripts/build-docs.ps1 -Check` | Passed |
| `az bicep format --file <changed-bicep>` | Passed for all three changed/new Bicep files |
| `az bicep build --file infra/main.bicep --outfile artifacts/azure-private/main.json` | Passed build/lint; full suite also builds all modules |
| Changed PowerShell AST parse | Passed before execution |
| `.venv\Scripts\python -m pytest -q` | Passed 60/60; no real source document or cloud calls |
| `.venv\Scripts\python -m ruff check .` | Passed |
| `.venv\Scripts\python -m ruff format --check .` | Passed, 62 files |
| `.venv\Scripts\python -m pip wheel --no-index --no-deps --no-build-isolation . --wheel-dir artifacts/dist` | Passed, no package downloads |
| `azd auth login --check-status --no-prompt` | Passed |
| MCP `validate_azure_yaml` | Passed official stable schema |
| `./scripts/preflight.ps1` | Passed actual target/provider/operator/model/quota/DI S0 checks |
| `azd package --no-prompt --environment handwriting-poc` | Passed; no hosted application services |
| `azd provision --preview --environment handwriting-poc --no-prompt` | Corrected preview passed; seven primary creates in dedicated scope, no existing-resource modifications/deletions |
| Effective permission/policy inspection | Nine management writes verified; three initiatives/11 members reviewed, not applicable to proposed AI/monitoring types |
| Publishable-source privacy scan | 165 files, no actual target IDs, IP or six generated resource names found |

No new package, image or action version is introduced by this infrastructure work.
Services are standard Azure offerings under the target subscription, not marketplace
or reserved-capacity purchases. Real-target logs/ARM outputs remain ignored/private.
Provisioned role, firewall, model and read-only endpoint checks are still required
after deployment. A successful preview is not a deployment or recognition-quality claim.

## Deployment and live verification

- 2026-10-29: `azd provision --environment handwriting-poc --no-prompt` completed.
  Immediately reconfirmed explicit subscription/tenant/region, core/two AI opt-ins,
  pinned model/capacity, current IPv4 and previously nonexistent dedicated RG.
  Raw provisioning output was captured privately; only sanitized type/status progress
  was displayed. No global subscription switch or provider registration.
- Actual Foundry and DI accounts, project, model and both monitoring resources are
  Succeeded. Regional Standard model is GPT-4.1 `2025-04-14`, capacity 10,
  `NoAutoUpgrade`. Both accounts disable keys and allow exactly the approved IPv4
  with default Deny, no bypass and no VNet rules. Retention/cap are 30 days/1 GB per day.
- Live RBAC: all three exact current-operator grants exist at intended
  account/project/DI scopes. Both accounts have one `AllMetrics`-only diagnostic
  setting targeting the same dedicated workspace; no enabled request/content logs.
- Inventory contains only the two AI accounts, project and two monitoring resources;
  the model child was queried separately. No unrelated hosting/storage/VM resources.
  `azd show --environment handwriting-poc --no-prompt` passed.
- **Unresolved blocker:** authenticated metadata GETs to DI model listing, OpenAI
  model listing and Foundry project connection listing return HTTP 403:
  `Access denied due to Virtual Network/Firewall rules.` No content was submitted.
  A native PowerShell HTTP test with an explicitly target-bound Entra token returned
  the same DI/OpenAI error; it is not just an Azure CLI response-shape issue.
- The configured single IP matches fresh uncached public-egress checks from native
  PowerShell and Python HTTP. DI resolves IPv4 only and uses the correct custom
  subdomain. No explicit HTTP(S)/ALL_PROXY environment settings were present.
  These checks do **not** prove which source address/network identity the Azure AI
  gateway sees. Exact cause (routing, network identity or propagation) is unconfirmed.
  Do not broaden firewall rules, enable trusted-service bypass or claim usable access.
- A verification harness initially expected a wrapped diagnostic-list response;
  this CLI returns a flat list. Corrected the harness and verified actual metrics-only
  state; no infrastructure change was needed.
- Actual endpoint URLs are retained in ignored `artifacts/azure-private/endpoints.json`
  and specific azd values, never in the public plan. Raw verification/policy/role
  evidence is in the same ignored directory. No document upload/inference/paid model
  or DI processing calls, destructive cleanup, application hosting or live CLI wiring.
