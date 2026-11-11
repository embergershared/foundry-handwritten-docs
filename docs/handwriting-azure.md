# Handwriting PoC: Azure recognition resources

The local CLI remains offline-only. These deployment assets prepare recognition
resources; provisioning them does **not** authorize uploading a document, running
inference, changing the CLI or claiming recognition quality. See
[the PoC guide](handwriting-poc.md) and [the deployment contract](../.azure/deployment-plan.md).

## Minimal composition

Use the existing subscription-scope azd/Bicep entry point. The `core` profile still
defaults to one resource group and monitoring only. Explicit `aiFoundry` and
`documentIntelligence` feature overrides add:

| Resource | Configuration |
|---|---|
| Foundry | AIServices S0, project, system identities, disabled key authentication |
| Vision deployment | GPT-4.1 `2025-04-14`, regional Standard, 10 capacity units / 10,000 TPM |
| Document Intelligence | Single-service FormRecognizer S0, custom subdomain, Entra-only |
| Operator RBAC | Account-scoped OpenAI User, project-scoped Azure AI User, DI-scoped Cognitive Services User |
| Diagnostics | `AllMetrics` only to this environment's existing Log Analytics workspace |

Everything belongs to the **same dedicated environment resource group**. No hosting,
storage, queues, Search, Key Vault, Bastion, NAT or VMs are needed. Do not initialize
another template over this repository. Existing private/full profiles are unchanged;
membership in the module catalog never enables a service.

## Explicit network exception

AI public access defaults to Disabled. The current composition has no AI private
endpoints, so opting in requires separate approval for `Enabled` and exactly one
canonical workstation public IPv4. Both service ACLs default Deny. Foundry explicitly
sets bypass None; FormRecognizer does not support trusted-service bypass and rejects
even a `bypass: None` property, so the DI module deliberately omits that property.
An empty IP never permits all networks. Preflight rejects CIDRs, IPv6, loopback and
private addresses. Validate the actual egress path; a VPN/proxy/IP change or IPv6
mismatch must fail closed, not trigger an unrestricted fallback.

The existing core Azure Monitor endpoints stay public and Entra-authenticated; they
cannot use the AI account IP rules. Do not enable audit/request/response logging,
prompt/completion telemetry or document content. Keep target IDs, resource names,
endpoint hostnames, firewall addresses, deployment logs and ARM outputs in ignored
local state, not public workflow logs or this repository. Public CI tests use only
synthetic configuration and never deploy this workload.

## Local configuration

First approve a concrete plan, target subscription/tenant/region and network choice.
Use a new environment; confirm the computed RG does not already exist. Never switch
the global Azure CLI subscription implicitly. Exact target values stay in ignored
`.azure/` state; tenant naming entries stay in ignored `infra/core/tenant-codes.json`.

**PowerShell (workstation)**, after selecting the isolated azd environment:

```powershell
Set-Location 'C:\path\to\foundry-handwritten-docs'
azd env set DEPLOYMENT_PROFILE core
azd env set AZURE_FEATURE_OVERRIDES_JSON '{"aiFoundry":true,"documentIntelligence":true}'
azd env set AZURE_AI_PUBLIC_NETWORK_ACCESS Enabled
# Supply these locally; never commit them or dump the complete environment.
$approvedIpv4 = Read-Host 'Approved workstation public IPv4'
$operatorId = Read-Host 'Approved Entra operator object ID'
azd env set AZURE_AI_ALLOWED_CLIENT_IPV4 $approvedIpv4
azd env set AZURE_OPERATOR_PRINCIPAL_IDS $operatorId
azd env set AZURE_VISION_DEPLOYMENT handwriting-vision
azd env set AZURE_VISION_MODEL gpt-4.1
azd env set AZURE_VISION_MODEL_VERSION 2025-04-14
azd env set AZURE_VISION_CAPACITY 10
```

The existing preprovision hook encodes feature overrides and seeds naming/tags.
AI operators must be explicit, including in core; do not silently discover or grant
roles to arbitrary directory users. Preflight reads model SKU metadata from
`model.skus` and checks actual regional service usage. It never substitutes global
capacity or requests a quota increase. Generic quota-provider availability is not
proof that Cognitive Services model quota is available.

Default environment values match the Bicep parameters. Model name/version/capacity
are configurable but must pass availability, lifecycle and quota gates and the
plan's approval; model version `latest` is forbidden. GPT-4.1 is a temporary baseline
with advertised retirement on 2027-04-14; reassess by 2027-03-01. No automatic upgrade.

## Validation and deployment

Follow `azure-prepare` -> `azure-validate` -> `azure-deploy`, not an ad-hoc resource
creation script. Parse changed PowerShell before execution. Run the existing full
infrastructure suite, catalog/docs checks, Bicep build/lint, Python regression checks,
packaging and a target-specific `azd provision --preview` before provisioning.
Review policy, permission to write scoped role assignments, provider registration,
regional quota, names, capacity, selected environment and proposed RG boundaries.
Capture real-target output privately and inspect it before publishing any summary.

After provisioning, verify actual states, the pinned regional model, disabled keys,
both default-deny single-IP ACLs with no bypass, the three intended RBAC scopes and metrics-only
diagnostics. Use authenticated, read-only model-list/metadata endpoints to check
access; **do not** submit document bytes, prompts or images for a smoke test.
Outputs expose DI/OpenAI/project endpoints and model/deployment metadata, never keys.

S0 DI is metered per page and Standard inference per token. No reserved model
capacity or hosted compute is selected. Monitoring ingestion may incur charges;
the daily ingestion cap is **not** a spending cap. Check current prices before a
separately approved data pilot. A partially failed deployment is not success;
retain evidence and review recovery. Deletion, purge or replacement needs separate
authorization; never invoke `azd down` as an automatic failure handler.

## Microsoft references

- [Document Intelligence authentication and Studio prerequisites](https://learn.microsoft.com/azure/ai-services/document-intelligence/quickstarts/get-started-studio)
- [Disable local authentication](https://learn.microsoft.com/azure/ai-services/disable-local-auth)
- [Azure AI virtual networks and firewalls](https://learn.microsoft.com/azure/ai-services/cognitive-services-virtual-networks)
- [Azure OpenAI deployment types](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/deployment-types)
