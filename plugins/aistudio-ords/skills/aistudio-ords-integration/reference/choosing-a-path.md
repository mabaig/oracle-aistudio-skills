# Choosing a path: three ways to reach ORDS

AI Studio offers three ways to call an external REST API. Nothing in the product
compares them, so most developers find one, hit a wall, and start over. Run the
probes in [setup-and-preflight.md](setup-and-preflight.md) first, then pick
deliberately using the table below.

## The decision

| | **External REST Tool** | **Connector** | **NonFusionOracleSource BO** |
|---|---|---|---|
| Authored by CLI | Yes, fully | Partly (staged, interactive) | Yes, fully |
| **Credentials configurable from CLI** | **No (hard blocked)** | **Yes** | No (the datasource is pre-created) |
| **Needs connector/KM API access** | No | **Yes** (`401` here blocks the path) | No |
| Import from OpenAPI | No; endpoints are hand-written | Yes | No; explicitly unsupported |
| Workflow node | `EXTERNAL_REST` | `TOOL` | `BO_FUNCTION` |
| Best when | ORDS is open, or you will finish auth in the UI | ORDS needs Basic/OAuth2, you have a spec, and connector APIs answer | An Oracle Data Source for this ATP already exists on the pod |

**The two most important rows are credentials and connector access.** They are
the walls almost everyone hits.

## Decision flow

```
Does the ORDS module need credentials?  (anonymous curl → 401 means yes)
├─ no  → External REST. The CLI's authInfo "none" costs you nothing.
└─ yes
   ├─ Does an Oracle Data Source for this ATP already exist on the pod?
   │    (list-bo-data-source-applications) → yes → consider NonFusionOracleSource BO
   ├─ Do the connector/KM probes succeed? (search-connector-definitions, list-km-connectors)
   │    ├─ yes → Connector (credentials collected programmatically, reproducible)
   │    └─ 401 → fix the IDCS scope / role first, or…
   └─ External REST + one manual UI auth step per environment
```

## If your ORDS endpoint needs credentials, read this first

The CLI refuses to write authentication into an External REST tool. This is a
deliberate block, not a bug:

> External REST tools created through the CLI must use authInfo.type "none".
> Add authentication in the UI instead.

Credential-shaped fields are rejected outright:

> Credential field "&lt;name&gt;" cannot be provided through the tool CLI.
> Add authentication in the UI instead.

The backend supports `basic`, `oauth2_client_credentials`,
`oauth2_user_assertion`, `oauth2_resource_owner`, and `oci_api_signature_1_0`,
but the CLI will not author any of them. The `--credential-type`,
`--credentials` and `--oauth` flags on tool creation reach **only** the MCP
branch; they have no effect on an OpenAPI or REST tool.

So there are exactly two honest routes to an authenticated ORDS call:

1. **External REST + UI hand-off.** Create the unauthenticated draft from the
   CLI, **save it to the pod**, then add credentials in the UI. Fast, but the
   tool is unusable until a human finishes it, and that step cannot be scripted
   or replayed in CI. Live test recording fails with ORDS's HTML
   `401 Unauthorized` page until it is done.
2. **Connector.** The staged Connector Instance flow is the only path where
   credentials are collected programmatically. It needs connector API access.
   If the preflight probes return `401`, this route is closed until the IDCS
   client scope or the user's role is fixed.

See [auth-on-atp.md](auth-on-atp.md) for both routes step by step.

## Recommendations by situation

**Read-only ORDS, open or IP-restricted, under ~15 endpoints**
→ **External REST Tool.** Simplest path. With no credentials, the CLI block
costs you nothing. This is what most ORDS reporting endpoints look like.

**ORDS behind OAuth2 client credentials, connector APIs reachable**
→ **Connector.** Subset and enrich the spec first
([spec-handling.md](spec-handling.md)). Do not start with External REST and
hope to add auth later unless you accept a permanent manual step.

**ORDS behind OAuth2, connector APIs return 401, deadline now**
→ **External REST + UI hand-off**, with the endpoint count trimmed to what the
agent needs ([external-rest-endpoints.md](external-rest-endpoints.md)). Keep the
subset spec anyway. When connector access is fixed, the switch is an import,
not a rewrite.

**An Oracle Data Source for this ATP instance already exists on the pod**
→ **NonFusionOracleSource BO.** Check first with
`list-bo-data-source-applications`. The listing shows data source names, not
connection targets, so confirm with the pod admin which database each one
points at. You cannot create the datasource yourself; that requires
credentials and is a pod-admin task.

**A large AutoREST schema (dozens of tables)**
→ **Connector**, and subset the spec first. See
[spec-handling.md](spec-handling.md).

## Why endpoint count matters

External REST endpoints are hand-authored; there is no
`do-create-tool --spec-file`. Each endpoint means writing `name`,
`description`, `operationType`, `resourcePath` (with `{tokens}`), `headers[]`
and, for writes, `bodyTemplate`. Every workflow node that calls one also needs
an `outputSpecification`, because no response schema is inferred.

For scale: a production tool we built carries **14 hand-authored endpoints in a
single `.tool` file**. That is tolerable once and painful to maintain. Past
roughly 15 endpoints, the Connector path's spec import pays for its extra setup.
Either way, give the agent only the operations it needs. A 6-operation tool out
of a 25-operation module is normal.

## What does not change whichever path you pick

- The ORDS response envelope still has to be modelled by hand on every
  workflow node. See [ords-response-contract.md](ords-response-contract.md).
- The generated spec's placeholder bodies and missing operationIds must be
  fixed by hand. See [ords-discovery.md](ords-discovery.md).
- `family` and `product` are required on tool creation for all three paths.
- Run `validate-tool` before `do-save-tool`. Save remotely when the user has
  asked to build on the pod, or when a later step (UI auth, test recording)
  requires the artifact to exist there.

## Delegation

Every command named here belongs to the base `aistudio` skill. Read that skill
and its operation-specific references at the moment you need a command
signature, never from memory and never from this file. This file tells you
*which* path to take; `aistudio` tells you how to walk it.
