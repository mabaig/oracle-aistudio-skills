# Choosing a path: three ways to reach ORDS

AI Studio offers three ways to call an external REST API. Nothing in the product
compares them, so most developers find one, hit a wall, and start over. Pick
deliberately using the table below before you create anything.

## The decision

| | **External REST Tool** | **Connector** | **NonFusionOracleSource BO** |
|---|---|---|---|
| Authored by CLI | Yes, fully | Partly — staged, interactive | Yes, fully |
| **Credentials configurable from CLI** | **No — hard blocked** | **Yes** | No — datasource is pre-created |
| Import from OpenAPI | No — endpoints hand-written | Yes | No — explicitly unsupported |
| Workflow node | `EXTERNAL_REST` | `TOOL` | `BO_FUNCTION` |
| Best when | ORDS is open, or you will finish auth in the UI | ORDS needs Basic/OAuth2 and you have a spec | An Oracle Data Source already exists on the pod |

**The single most important line in this table is the credentials row.** It is
the wall almost everyone hits.

## If your ORDS endpoint needs credentials, read this first

The CLI refuses to write authentication into an External REST tool. This is a
deliberate block, not a bug:

> External REST tools created through the CLI must use authInfo.type "none".
> Add authentication in the UI instead.

Credential-shaped fields are rejected outright:

> Credential field "&lt;name&gt;" cannot be provided through the tool CLI.
> Add authentication in the UI instead.

The backend supports `basic`, `oauth2_client_credentials`,
`oauth2_user_assertion`, `oauth2_resource_owner`, and `oci_api_signature_1_0` —
the CLI simply will not author any of them. The `--credential-type`,
`--credentials` and `--oauth` flags on tool creation reach **only** the MCP
branch; they are silently irrelevant to an OpenAPI or REST tool.

So there are exactly two honest routes to an authenticated ORDS call:

1. **External REST + UI hand-off.** Create the unauthenticated draft from the
   CLI, then add credentials in the UI. Fast, but the tool is not usable until a
   human finishes it, and that step cannot be scripted or replayed in CI.
2. **Connector.** The staged Connector Instance flow is the only path where
   credentials are collected programmatically. More setup, but it ends with a
   working credentialed integration.

See [auth-on-atp.md](auth-on-atp.md) for both routes step by step.

## Recommendations by situation

**Read-only ORDS, open or IP-restricted, under ~15 endpoints**
→ **External REST Tool.** Simplest path, and with no credentials the CLI block
costs you nothing. This is what most ORDS reporting endpoints look like.

**ORDS behind OAuth2 client credentials or Basic auth**
→ **Connector.** Do not start with External REST and hope to add auth later
unless you accept a permanent manual step.

**An Oracle Data Source for this ATP instance already exists on the pod**
→ **NonFusionOracleSource BO.** Check first with
`list-bo-data-source-applications`; if one is listed, this is the least work.
You cannot create the datasource yourself — that requires credentials and is a
pod-admin task.

**A large AutoREST schema (dozens of tables)**
→ **Connector**, and subset the spec first. See
[spec-handling.md](spec-handling.md).

## Why endpoint count matters

External REST endpoints are hand-authored — there is no
`do-create-tool --spec-file`. Each endpoint means writing `name`,
`description`, `operationType`, `resourcePath`, `parameterDefinitions[]` and
`headers[]` by hand, plus an `outputSpecification` on every workflow node that
calls it, because no response schema is inferred.

For scale: a production tool we built carries **14 hand-authored endpoints in a
single `.tool` file**. That is tolerable once and painful to maintain. Past
roughly 15 endpoints, the Connector path's spec import pays for its extra setup.

## Whichever path: split read from write

An agent is offered every endpoint of a tool attached to it. Put `GET`
endpoints in one tool and write endpoints in another, and attach the write tool
only to an agent behind a confirmation gate. See
[agent-safety-and-resilience.md](agent-safety-and-resilience.md).

## What does not change whichever path you pick

- The ORDS response envelope still has to be modelled by hand on every
  workflow node. See [ords-response-contract.md](ords-response-contract.md).
- `family` and `product` are required on tool creation for all three paths.
- Run `validate-tool` before `do-save-tool`, and save only when the user
  explicitly asks to persist remotely.

## Delegation

Every command named here belongs to the base `aistudio` skill. Read that skill
and its operation-specific references at the moment you need a command
signature — never from memory, and never from this file. This file tells you
*which* path to take; `aistudio` tells you how to walk it.
