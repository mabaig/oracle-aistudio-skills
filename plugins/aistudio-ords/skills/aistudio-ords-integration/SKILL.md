---
name: aistudio-ords-integration
description: Build Oracle Fusion AI Studio agentic apps and workflows on top of an existing Oracle REST Data Services (ORDS) estate on ATP — constructing ORDS URLs, reading the ORDS OpenAPI and metadata catalogs, choosing between the External REST, Connector and NonFusionOracleSource paths, handling ORDS auth on ATP, modelling the items/hasMore/count/links envelope into a workflow node's outputSpecification, subsetting AutoREST OpenAPI specs, diagnosing 401/404/555 errors, keeping agents safe around write endpoints, and regression-testing ORDS-backed workflows. Use whenever connecting AI Studio to ORDS, APEX or an Autonomous Database REST endpoint, wiring a REST API into an agentic app or workflow, choosing a tool type for an external API, debugging ORDS auth, pagination or an empty panel, or reusing ORDS modules originally built for APEX or VBCS. Triggers "ORDS", "Oracle REST Data Services", "ATP", "Autonomous Database", "APEX REST", "AutoREST", "ords/schema/module", "open-api-catalog", "metadata-catalog", "ORDS OpenAPI", "ORDS URL", "connect AI Studio to my REST API", "External REST tool", "connector definition", "hasMore", "items array", "outputSpecification", "authInfo none", "401 from ORDS", "555 error", "panel shows no data", "agentic app on my own data".
---

# ORDS → Fusion agentic apps

A method for turning an ORDS estate — typically one built years ago for APEX or
VBCS — into agentic apps and workflows in Oracle Fusion AI Studio.

This skill supplies the ORDS-specific knowledge AI Studio does not ship: how to
construct ORDS URLs and read its catalogs, which of three REST paths to take,
how authentication actually works on ATP, how to model the ORDS response
envelope, how to keep agents safe around write endpoints, and how to test and
diagnose the result. It performs no artifact operations itself.

## Delegation — read this first

This skill is a domain layer over the base `aistudio` skill. It owns *what to do
and why*; `aistudio` owns *how*.

- Delegate every artifact operation — discovery, creation, modification,
  validation, save, fetch, publish — to `aistudio`.
- Read the current local `aistudio` skill and its operation-specific references
  at the moment you need a command signature. Never from memory, never from a
  cached copy, and never from this file.
- Do not invent AI Studio commands, flags, file paths, schema fields, node
  types, or payload shapes. If an implementation detail is needed, hand off.
- Never modify the base `aistudio` skill.

Command names appear in this skill only as signposts. Oracle ships monthly;
signatures change and this skill deliberately does not restate them.

## Where to start

| You want to… | Read |
|---|---|
| Build an integration from zero | [reference/end-to-end-walkthrough.md](reference/end-to-end-walkthrough.md) |
| Work out the exact URL, or get a module's OpenAPI document | [reference/ords-url-and-catalog.md](reference/ords-url-and-catalog.md) |
| Fix a `401`, `404`, `555` or an empty panel | [reference/diagnosing-ords.md](reference/diagnosing-ords.md) |
| Let an agent call write endpoints safely | [reference/agent-safety-and-resilience.md](reference/agent-safety-and-resilience.md) |

## The six steps

**0 · Confirm the environment.** Check which Fusion environment and user the
CLI is authenticated as, and that you can reach ORDS from your machine. Tool,
workflow and app ids are per environment.

**1 · Inventory the ORDS surface.** List the modules and templates the app needs
— from the `USER_ORDS_*` views ([reference/ords-setup-sql.md](reference/ords-setup-sql.md))
or the OpenAPI catalog ([reference/ords-url-and-catalog.md](reference/ords-url-and-catalog.md)).
For each endpoint record: method, full path, whether it needs credentials,
roughly how many rows it returns, whether the response is enveloped, and
whether an agent may call it. Prove each one from a shell with
`scripts/ords_catalog.py check` before going further.

**2 · Choose a path.** Read [reference/choosing-a-path.md](reference/choosing-a-path.md).
Three exist — External REST Tool, Connector, and `NonFusionOracleSource`
Business Object — and AI Studio never compares them. The deciding factor is
almost always credentials: **the CLI cannot write authentication into an
External REST tool**, so a credentialed ORDS endpoint either takes the Connector
path or accepts a permanent manual UI step.

**3 · Settle authentication.** Read [reference/auth-on-atp.md](reference/auth-on-atp.md)
*before* creating anything. Deciding auth after the tool exists is the most
common way these integrations dead-end. Sample SQL for roles, privileges and
OAuth clients is in [reference/ords-setup-sql.md](reference/ords-setup-sql.md).

**4 · Create the tool.** Hand off to `aistudio`. Build the instance URL and
resource paths with [reference/ords-url-and-catalog.md](reference/ords-url-and-catalog.md):
the instance URL ends at the schema alias, resource paths start with the module
base path, and every `:name` becomes `{name}`. On the External REST path, start
from [assets/ords-endpoint-template.json](assets/ords-endpoint-template.json) or
generate draft blocks with `scripts/ords_catalog.py endpoints`. On the Connector
path, [reference/spec-handling.md](reference/spec-handling.md) covers the
OpenAPI dialect constraint and subsetting. Put read and write endpoints in
separate tools ([reference/agent-safety-and-resilience.md](reference/agent-safety-and-resilience.md)).
→ *Verify: `validate-tool` passes. Save remotely only if the user asks. If auth
is added in the UI, prove it with a live call — not by reading the `.tool` file.*

**5 · Wire the workflow node.** The node's `outputSpecification` is hand-written
and nothing is inferred from your API. Read
[reference/ords-response-contract.md](reference/ords-response-contract.md) —
ORDS returns three different shapes, and assuming the envelope is a real bug.
Start from [assets/ords-output-specification.json](assets/ords-output-specification.json).
Fetch only on the branches that need the data, guard each fetch, and gate any
write behind a confirmation step in the graph.
→ *Verify: the node returns data and every downstream expression references a
declared field.*

**6 · Test it.** Read [reference/testing-ords-workflows.md](reference/testing-ords-workflows.md).
Record at the ORDS boundary, replay from file, assert the path as well as the
answer, cover the empty collection — and keep one live smoke run.
→ *Verify: the suite passes with recorded data, an empty-result variation
exercises the empty-state branch, and a live run shows `200` on every ORDS node.*

## Things that catch people out

**Authentication cannot be scripted on the External REST path.** The CLI forces
`authInfo.type = "none"` and rejects credential-shaped fields. That is a
deliberate secret-hygiene decision, but it means an authenticated External REST
tool always needs a human in the UI — on every environment you promote to.

**The `.tool` file does not tell you whether auth works.** A tool whose OAuth2
was added in the UI can still read `authInfo.type: "none"` when fetched. Only a
live call proves it, and a later CLI save can undo it. Re-test after every save.

**The URL is several settings, not one.** Schema alias (not necessarily the
schema name), module base path, and template pattern with `:name` parameters.
Split at the alias: instance URL on one side, resource path on the other.

**ORDS pages at 25 rows by default.** Baking `?limit=200` into the resource path
is the popular fix and it is wrong: it fails silently the moment row 201 exists,
while `hasMore: true` sits unread in the response. Expose `limit` and `offset`
as parameters and handle `hasMore`.

**Not every ORDS response is enveloped.** Handler modules returning a composed
object — KPI and summary endpoints especially — return that object bare, with no
`items` or `hasMore`, often sitting right beside enveloped endpoints in the same
module.

**An agent is offered every endpoint of an attached tool.** Including the
`DELETE`. Split read and write tools, attach the write tool only to an agent
behind a confirmation gate in the workflow graph, and back it with a read-only
ORDS client. Prompt instructions are not a control.

**One failing call can take down the whole response.** A failing ORDS fetch
before the app-stage router fails every stage; a `4xx`/`5xx` inside an agent can
abort its reply. And `555` means the handler SQL failed — fix the SQL, not the
tool.

**Green tests, empty app.** Replayed tests never touch the live endpoint. Keep a
live smoke run after every deploy, privilege change and tool save.

**Trim the payload in SQL, not the workflow.** ORDS rows arrive with audit
columns, surrogate keys and denormalised duplicates. Every one is tokens spent
and something the model can misquote. A handler selecting the eight columns the
agent needs beats `SELECT *` plus a downstream transform.

## Helper script

[scripts/ords_catalog.py](scripts/ords_catalog.py) — Python 3, standard library
only, never prints credentials:

| Command | Does |
|---|---|
| `modules` | Lists modules and objects in the OpenAPI catalog |
| `spec` | Downloads one module's OpenAPI document and reports its dialect |
| `endpoints` | Turns an OpenAPI document into draft External REST endpoint blocks |
| `subset` | Keeps selected paths plus the components they reference |
| `check` | Calls one endpoint and reports status, envelope shape and paging |

Network commands accept `--auth client-credentials` (reads `ORDS_CLIENT_ID` and
`ORDS_CLIENT_SECRET` from the environment) or `--bearer-env NAME`.

## Worked example

[assets/example/](assets/example/) contains a small service-ticket module — DDL,
ORDS module definition, sample responses, a sample OpenAPI document, and
endpoint blocks for the tool. It is deliberately tiny, runs from zero on a
clean pod, and exercises all three response shapes.
[reference/end-to-end-walkthrough.md](reference/end-to-end-walkthrough.md) walks
it through every step.

## Scope

This skill covers reaching ORDS from AI Studio. It does not cover writing ORDS
modules in depth, ATP administration, or AI Studio app design beyond the panel
that consumes an ORDS-backed workflow. For app and workflow authoring, defer to
`aistudio` and its own references.
