---
name: aistudio-ords-integration
description: Build Oracle Fusion AI Studio agentic apps and workflows on top of an existing Oracle REST Data Services (ORDS) estate on ATP. Covers installing and preflighting Oracle's base aistudio skill in Claude Code, finding and reading the ORDS OpenAPI catalog (open-api-catalog URL anatomy, schema alias, module base path), fixing what the generated spec gets wrong (body_text placeholder bodies, missing operationIds, undeclared envelopes), choosing between the External REST, Connector and NonFusionOracleSource paths, ORDS OAuth2 on ATP, authoring External REST endpoints with tokens, modelling the items/hasMore/count/links envelope into outputSpecification, per-handler page sizes, writing back to ORDS from app actions, and regression-testing ORDS-backed workflows. Use whenever connecting AI Studio to ORDS, APEX or an Autonomous Database REST endpoint, building an agentic app on an ORDS module, wiring a REST API into a workflow, choosing a tool type for an external API, debugging ORDS auth, 401s, 404s or pagination in a workflow, or reusing ORDS modules built for APEX or VBCS. Triggers "ORDS", "Oracle REST Data Services", "ATP", "Autonomous Database", "APEX REST", "AutoREST", "open-api-catalog", "ords/schema/module", "build app using my ords module", "connect AI Studio to my REST API", "External REST tool", "connector definition", "body_text", "hasMore", "items array", "outputSpecification", "authInfo none", "401 from ORDS", "Unauthorized HTML page", "agentic app on my own data".
---

# ORDS → Fusion agentic apps

A method for turning an ORDS estate, typically one built years ago for APEX or
VBCS, into agentic apps and workflows in Oracle Fusion AI Studio.

This skill supplies the ORDS-specific knowledge AI Studio does not ship:

- how to find and read an ORDS API
- which of three REST paths to take
- how authentication actually works on ATP
- how to model the ORDS response envelope
- how to write back safely
- how to test the result

It performs no artifact operations itself.

## Delegation: read this first

This skill is a domain layer over Oracle's base `aistudio` skill. It owns *what
to do and why*; `aistudio` owns *how*.

- **The base skill is not part of this plugin.** If `aistudio` is not in the
  skill list, stop and install it first; see
  [reference/setup-and-preflight.md](reference/setup-and-preflight.md). For
  Claude Code it must be unzipped under `.claude/skills/aistudio/`, not
  `.agents/skills/`.
- Delegate every artifact operation (discovery, creation, modification,
  validation, save, fetch, test) to `aistudio`.
- Read the current local `aistudio` skill and its operation-specific references
  at the moment you need a command signature. Never from memory, never from a
  cached copy, and never from this file.
- Do not invent AI Studio commands, flags, file paths, schema fields, node
  types, or payload shapes. If an implementation detail is needed, hand off.
- Never modify the base `aistudio` skill.

Command names appear in this skill only as signposts. Oracle ships monthly;
signatures change, and this skill deliberately does not restate them.

## The method

**0 · Preflight.** Read [reference/setup-and-preflight.md](reference/setup-and-preflight.md).
Check four things:

- the base skill is installed
- `env.properties` points at the pod and `whoami` works
- the connector and Knowledge Management APIs answer for this user. A `401` here
  closes the Connector path before you have chosen it.
- ORDS credentials live in a git-ignored file, never in chat

→ *Verify: `whoami` prints the user; connector probe result recorded.*

**1 · Inventory the ORDS surface.** Read [reference/ords-discovery.md](reference/ords-discovery.md).
Build the catalog URL (`https://<adb-host>/ords/<schema-alias>/open-api-catalog/`),
take each module's spec from its `canonical` link, and run
`scripts/ords_openapi.py inventory` then `probe`. For each endpoint record:

- method and path
- whether it needs credentials
- the **real** page size
- the response shape
- whether the spec's request body is a `body_text` placeholder

Recover placeholder bodies from the handler source
([assets/sql/ords-introspection.sql](assets/sql/ords-introspection.sql)).
→ *Verify: every operation the agent needs has a known shape, page size and body.*

**2 · Choose a path.** Read [reference/choosing-a-path.md](reference/choosing-a-path.md).
Three exist (External REST Tool, Connector, and a `NonFusionOracleSource`
Business Object), and AI Studio never compares them. The deciding factors are
credentials and connector access. **The CLI cannot write authentication into an
External REST tool**, and the Connector path needs connector APIs that may
return `401`.

**3 · Settle authentication.** Read [reference/auth-on-atp.md](reference/auth-on-atp.md)
*before* creating anything. Use a dedicated ORDS OAuth client for AI Studio
([assets/sql/create-oauth-client.sql](assets/sql/create-oauth-client.sql)), and
prove the token exchange from a shell.

**4 · Build the spec and the tool.** Hand off to `aistudio`. Always produce an
agent-sized, enriched spec with `scripts/ords_openapi.py subset`, then fix the
flagged items by hand ([reference/spec-handling.md](reference/spec-handling.md)).
On the Connector path, import that spec. On the External REST path, hand-write
endpoints with every workflow-set value as a `{token}`
([reference/external-rest-endpoints.md](reference/external-rest-endpoints.md),
[assets/ords-endpoint-template.json](assets/ords-endpoint-template.json)).
→ *Verify: `validate-tool` passes; a CLI dry run shows the tokens with the right
`location`.*

**5 · Wire the workflow.** Each node's `outputSpecification` is hand-written;
nothing is inferred from your API. Read
[reference/ords-response-contract.md](reference/ords-response-contract.md) and
start from [assets/ords-output-specification.json](assets/ords-output-specification.json).
For app-backed workflows, the shape that works is:

1. shared ORDS fetches
2. one CODE node that groups, trims and flags truncation
3. the app-stage router
4. a dedicated LLM terminal per stage

Test the CODE node locally with `scripts/code_node_harness.mjs`. For actions
that write to ORDS, read [reference/write-back-actions.md](reference/write-back-actions.md).
→ *Verify: `validate-workflow` passes; every downstream expression references a
declared field.*

**6 · Test it.** Read [reference/testing-ords-workflows.md](reference/testing-ords-workflows.md).
Save the tools and workflow to the pod, and add UI auth to authenticated tools.
Then record the InitDisplay baseline at the ORDS boundary, replay the other
stages, assert paths, cover the empty collection, and point write recordings at
non-production data.
→ *Verify: the suite passes on recorded data, and an empty-result variation
exercises the empty-state branch.*

## Sample session (generic)

The shape of a real run, using the service-desk example. Replace the
placeholders; never put real hosts or secrets into shared files.

```bash
# 0. preflight
node .claude/skills/aistudio/scripts/aistudio.js whoami
node .claude/skills/aistudio/scripts/aistudio.js search-connector-definitions --query servicedesk   # 401? see auth-on-atp.md

# 1. inventory
S=<skill-dir>/scripts
python3 $S/ords_openapi.py catalog --host <adb-host> --alias <schema-alias>
python3 $S/ords_openapi.py inventory https://<adb-host>/ords/<schema-alias>/open-api-catalog/servicedesk/
set -a; . ./.env.local; set +a        # ORDS_CLIENT_ID / ORDS_CLIENT_SECRET, git-ignored
python3 $S/ords_openapi.py probe --token-url https://<adb-host>/ords/<schema-alias>/oauth/token \
        https://<adb-host>/ords/<schema-alias>/open-api-catalog/servicedesk/

# 4. agent spec (then fix placeholder bodies and add operationIds by hand)
python3 $S/ords_openapi.py subset module-spec.json --keep "GET /tickets" --keep "GET /summary" \
        --keep "POST /tickets/assign" --security OAuth2:clientCredentials -o agent-spec.json

# 5. unit-test the normalising CODE node against real ORDS JSON
node $S/code_node_harness.mjs --wf src/workflows/<workflow>.wf --context ctx.json --node BUILD_SNAPSHOT
```

Then, through the base skill:

1. create the tool
2. create the workflow nodes and edges, then prettify and validate
3. create the app, **creating its action before the prompts that call it**
4. save the drafts
5. add auth to the tool in the UI
6. run the workflow test sync loop

## Things that catch people out

**Authentication cannot be scripted on the External REST path.** The CLI forces
`authInfo.type = "none"`. An authenticated External REST tool always needs a
human in the UI, after the tool is saved, on every environment you promote to.
Until then, live calls get ORDS's HTML `401 Unauthorized` page. The test
recorder misreports that page as a "backend-truncated preview".

**Connector access is a separate permission.** `whoami` and workflow commands
can succeed while connector and KM APIs return `401`: a missing IDCS scope
(Oracle Boss Cloud (Spectra)) or connector role. Probe before choosing.

**The catalog URL uses the module base path, and the host segment uses the
schema alias.** Neither is necessarily the module or schema name. Follow the
catalog's `canonical` links.

**The generated spec lies about PL/SQL request bodies.** `{ "body_text": string }`
is the placeholder for `:body_text`; the real contract is in the handler
source. The spec also has no operationIds, and its response schemas usually
omit `hasMore`, `count`, `limit` and `offset`.

**Page size is per handler.** The module default is often 25, but handlers
override it (one real module ranged from 25 to 5000). Baking `?limit=200` into
the resource path fails silently at row 201. Make `limit` and `offset` tokens,
declare `hasMore`, and handle it.

**Only tokens reach the workflow.** An `EXTERNAL_REST` node's inputs are exactly
the endpoint's `{tokens}`. Put filters in the resource path as tokens. ORDS
binds empty values as `NULL`, so unused filters can be sent as `""`.

**Not every ORDS response is enveloped.** KPI and summary handlers return a
bare object, often beside enveloped endpoints in the same module.

**Trim the payload in SQL, not the workflow.** ORDS rows arrive with audit
columns, surrogate keys, denormalised duplicates, and sometimes non-person
accounts. A handler selecting the columns the agent needs beats `SELECT *` plus
a transform. When you can't change the SQL, use one tested CODE node.

**Writes are real, including in tests.** Re-validate every key against fresh
data before calling a write handler. Make handlers return real
`SQL%ROWCOUNT`-based counts. Remember that a live InvokeAction recording
performs the write.

## Bundled scripts and assets

| Path | What it is |
|---|---|
| [scripts/ords_openapi.py](scripts/ords_openapi.py) | `catalog`, `inventory`, `probe`, `subset` for ORDS OpenAPI specs. Standard-library Python; credentials only from env vars |
| [scripts/code_node_harness.mjs](scripts/code_node_harness.mjs) | Run a workflow's CODE nodes locally against recorded ORDS JSON |
| [assets/sql/ords-introspection.sql](assets/sql/ords-introspection.sql) | Deployed modules, handlers, page sizes, handler source, privileges, OAuth clients |
| [assets/sql/create-oauth-client.sql](assets/sql/create-oauth-client.sql) | A dedicated client-credentials client for AI Studio |
| [assets/ords-endpoint-template.json](assets/ords-endpoint-template.json) | External REST endpoint template with tokens |
| [assets/ords-output-specification.json](assets/ords-output-specification.json) | `outputSpecification` for the three ORDS shapes |
| [assets/example/](assets/example/) | Worked service-desk example, including protection, a write handler, an agent spec and a node |

## Worked example

[assets/example/](assets/example/) contains a small service-ticket module:

- DDL and the ORDS handler module
- sample responses covering all three shapes
- SQL to protect the module with OAuth2
- a truthful write handler
- the enriched agent OpenAPI spec
- External REST endpoints with tokens
- a normalised workflow node

It is deliberately tiny and runs from zero on a clean pod.

## Scope

This skill covers reaching ORDS from AI Studio: discovery, path choice, auth,
tool and spec authoring, response modelling, write-back safety and testing. It
does not cover general ORDS module design, ATP administration, or AI Studio app
design beyond the panels and actions that consume ORDS-backed workflows. For app
and workflow authoring, defer to `aistudio` and its own references.
