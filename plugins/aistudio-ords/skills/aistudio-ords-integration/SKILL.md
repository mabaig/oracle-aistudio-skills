---
name: aistudio-ords-integration
description: Build Oracle Fusion AI Studio agentic apps and workflows on top of an existing Oracle REST Data Services (ORDS) estate on ATP — choosing between the External REST, Connector and NonFusionOracleSource paths, handling ORDS auth on ATP, modelling the items/hasMore/count/links envelope into a workflow node's outputSpecification, subsetting AutoREST OpenAPI specs, and regression-testing ORDS-backed workflows. Use whenever connecting AI Studio to ORDS, APEX or an Autonomous Database REST endpoint, wiring a REST API into an agentic app or workflow, choosing a tool type for an external API, debugging ORDS auth or pagination in a workflow, or reusing ORDS modules originally built for APEX or VBCS. Triggers "ORDS", "Oracle REST Data Services", "ATP", "Autonomous Database", "APEX REST", "AutoREST", "ords/schema/module", "connect AI Studio to my REST API", "External REST tool", "connector definition", "hasMore", "items array", "outputSpecification", "authInfo none", "401 from ORDS", "agentic app on my own data".
---

# ORDS → Fusion agentic apps

A method for turning an ORDS estate — typically one built years ago for APEX or
VBCS — into agentic apps and workflows in Oracle Fusion AI Studio.

This skill supplies the ORDS-specific knowledge AI Studio does not ship: which
of three REST paths to take, how authentication actually works on ATP, how to
model the ORDS response envelope, and how to test the result. It performs no
artifact operations itself.

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

## The six steps

**1 · Inventory the ORDS surface.** List the modules and templates the app needs.
For each endpoint record: method, path, whether it needs credentials, roughly
how many rows it returns, and whether the response is enveloped. Endpoint count
and auth drive the next decision.

**2 · Choose a path.** Read [reference/choosing-a-path.md](reference/choosing-a-path.md).
Three exist — External REST Tool, Connector, and `NonFusionOracleSource`
Business Object — and AI Studio never compares them. The deciding factor is
almost always credentials: **the CLI cannot write authentication into an
External REST tool**, so a credentialed ORDS endpoint either takes the Connector
path or accepts a permanent manual UI step.

**3 · Settle authentication.** Read [reference/auth-on-atp.md](reference/auth-on-atp.md)
*before* creating anything. Deciding auth after the tool exists is the most
common way these integrations dead-end.

**4 · Create the tool.** Hand off to `aistudio`. On the Connector path,
[reference/spec-handling.md](reference/spec-handling.md) covers the OpenAPI
dialect constraint and why you should import a module spec rather than a whole
AutoREST schema. On the External REST path, start from
[assets/ords-endpoint-template.json](assets/ords-endpoint-template.json).
→ *Verify: `validate-tool` passes. Save remotely only if the user asks.*

**5 · Wire the workflow node.** The node's `outputSpecification` is hand-written
and nothing is inferred from your API. Read
[reference/ords-response-contract.md](reference/ords-response-contract.md) —
ORDS returns three different shapes, and assuming the envelope is a real bug.
Start from [assets/ords-output-specification.json](assets/ords-output-specification.json).
→ *Verify: the node returns data and every downstream expression references a
declared field.*

**6 · Test it.** Read [reference/testing-ords-workflows.md](reference/testing-ords-workflows.md).
Record at the ORDS boundary, replay from file, assert the path as well as the
answer, and cover the empty collection.
→ *Verify: the suite passes with recorded data, and an empty-result variation
exercises the empty-state branch.*

## Four things that catch people out

**Authentication cannot be scripted on the External REST path.** The CLI forces
`authInfo.type = "none"` and rejects credential-shaped fields. That is a
deliberate secret-hygiene decision, but it means an authenticated External REST
tool always needs a human in the UI — on every environment you promote to.

**ORDS pages at 25 rows by default.** Baking `?limit=200` into the resource path
is the popular fix and it is wrong: it fails silently the moment row 201 exists,
while `hasMore: true` sits unread in the response. Expose `limit` and `offset`
as parameters and handle `hasMore`.

**Not every ORDS response is enveloped.** Handler modules returning a composed
object — KPI and summary endpoints especially — return that object bare, with no
`items` or `hasMore`, often sitting right beside enveloped endpoints in the same
module.

**Trim the payload in SQL, not the workflow.** ORDS rows arrive with audit
columns, surrogate keys and denormalised duplicates. Every one is tokens spent
and something the model can misquote. A handler selecting the eight columns the
agent needs beats `SELECT *` plus a downstream transform.

## Worked example

[assets/example/](assets/example/) contains a small service-ticket module — DDL,
ORDS module definition, a trimmed OpenAPI spec, and the resulting tool and
workflow node. It is deliberately tiny and runs from zero on a clean pod.

## Scope

This skill covers reaching ORDS from AI Studio. It does not cover writing ORDS
modules, ATP administration, or AI Studio app design beyond the panel that
consumes an ORDS-backed workflow. For app and workflow authoring, defer to
`aistudio` and its own references.
