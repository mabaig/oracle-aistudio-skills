# Getting a usable OpenAPI spec out of ORDS

Only the Connector path consumes a spec. External REST endpoints are
hand-authored, and `NonFusionOracleSource` explicitly cannot load OpenAPI:

> Do not try to load OpenAPI for these sources.

Even on the External REST path, build the agent spec below anyway. It is the
cleanest inventory you will have, and it turns a later move to Connector into
an import rather than a rewrite.

## Where ORDS publishes specs

```
https://<adb-host>/ords/<schema-alias>/open-api-catalog/                      # index of modules
https://<adb-host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/   # one module's spec
https://<adb-host>/ords/<schema-alias>/metadata-catalog/                      # AutoREST objects, describedby links
```

The per-module URL ends in the module's **base path**, not its name. A module
named `servicedesk_v2` with `p_base_path => '/sd/'` is at
`…/open-api-catalog/sd/`. Take the URL from the index entry's `canonical` link
rather than building it. [ords-discovery.md](ords-discovery.md) covers URL
anatomy, auth on the catalog, and how to read the index.

A response's `links[rel=describedby]` also points at the metadata catalog entry
for that resource, which is a quick way to find the description of one endpoint
you already have working.

AutoREST-enabled objects publish per-object descriptions. A handler-based module
publishes one spec covering its templates. That is usually the better import,
because it describes the endpoints you actually designed.

## The dialect constraint

The spec type is **hardcoded** to `OPENAPI_3_0`. There is no `--spec-type` flag
and no Swagger 2.0 or OpenAPI 3.1 branch.

Modern ORDS emits OpenAPI 3.0 and imports cleanly. Older ORDS releases emit
Swagger 2.0. If yours does, convert to 3.0 before importing. The generator will
not do it, and the failure message will not mention dialect.

```bash
python3 <skill-dir>/scripts/ords_openapi.py inventory <spec-url-or-file>   # prints Dialect
```

`"openapi": "3.0.x"` imports. `"swagger": "2.0"` must be converted first.

## The generated spec is not agent-ready

ORDS generates the spec from handler metadata. Before importing, fix what
`inventory` flags (full table in
[ords-discovery.md](ords-discovery.md#what-the-generated-spec-gets-wrong)):

1. **Placeholder bodies.** Every PL/SQL handler shows `{ "body_text": string }`.
   Replace it with the real JSON schema from the handler source. A connector
   tool generated from the placeholder would send `{"body_text": …}` and the
   handler would reject it or silently do nothing.
2. **operationIds.** Add a stable, verb-first `operationId` to every operation
   (`listTickets`, `assignTickets`). They become tool/function names the model
   picks from.
3. **Descriptions.** Replace "Retrieve records from <module>" and "Implicit
   parameter" with what the operation returns, allowed values, formats and
   defaults. Say when an operation changes data.
4. **Envelope.** Declare `hasMore`, `count`, `limit`, `offset` on collection
   responses, and declare `limit` / `offset` as parameters.
5. **Security.** Keep one scheme and one flow, usually OAuth2
   `clientCredentials` with the `…/oauth/token` URL, so connector instance
   configuration asks for the right fields.

[../assets/example/07-agent-openapi.json](../assets/example/07-agent-openapi.json)
is the service-desk module after these fixes.

## Size: subset before importing

The spec is read whole and posted **inline as a single JSON string in one
request**. There is no chunking, no `$ref` bundling, no operation filtering, and
no client-side size cap. A large spec either succeeds or fails server-side, and
the failure will not tell you size was the problem.

An AutoREST-enabled schema with dozens of tables produces a very large spec, and
most of it describes endpoints your agent will never call. Handler modules also
accumulate admin, sync and logging endpoints that an agent must not see.

**Import a module, not a schema, and only the operations the agent needs.**

```bash
python3 <skill-dir>/scripts/ords_openapi.py subset module-spec.json \
  --keep "GET /tickets" --keep "GET /tickets/{reference}" --keep "GET /summary" \
  --keep "POST /tickets/assign" \
  --security OAuth2:clientCredentials \
  -o agent-spec.json
```

`subset` keeps the listed operations, prunes `components` to what they
reference (transitively), keeps one security scheme, and fails on a dangling
`$ref`. It warns about operations still carrying a placeholder body or no
`operationId`. Fix those by hand in `agent-spec.json`, then re-run `inventory`
until it reports no flags.

Fewer imported operations also means a shorter tool list for the agent to choose
from, which improves tool selection. Subsetting is a quality decision, not only
a size one.

## Two different auth questions

`--url-auth` authenticates **fetching the spec** when you pass `--spec-url`. It
is nested as `openApi: { url, urlAuth }` and has nothing to do with calls to the
API afterwards.

Because you should import an edited subset anyway, fetch the spec yourself and
pass `--spec-file`. That avoids `--url-auth` entirely.

Runtime auth is a separate problem; see [auth-on-atp.md](auth-on-atp.md).

## Failure handling

The base skill's guidance applies:

- Retry once with `--verbose`.
- Report the redacted route, resolved URL, auth mode, failure stage, and a
  curl-style command.
- If a definition id came back but the detail fetch failed, **do not generate
  again**. Fetch the definition by id instead; re-running creates duplicates.
- A `401` from definition search or generation, while other commands work, is an
  access problem, not a spec problem. See
  [setup-and-preflight.md](setup-and-preflight.md).

## Checklist

- [ ] Spec URL taken from the catalog `canonical` link (base path, not module name)
- [ ] Confirmed `openapi: 3.0.x`, converted if Swagger 2.0
- [ ] Importing a module spec, subset to the agent's operations
- [ ] No placeholder bodies; every operation has an `operationId` and a real description
- [ ] Envelope and paging parameters declared; one security scheme
- [ ] Subset validated: no dangling `$ref`, and `inventory` reports no flags
- [ ] Searched existing definitions before generating a new one
