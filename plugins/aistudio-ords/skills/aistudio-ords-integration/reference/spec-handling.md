# Getting a usable OpenAPI spec out of ORDS

Only the Connector path consumes a spec. External REST endpoints are
hand-authored and `NonFusionOracleSource` explicitly cannot load OpenAPI:

> Do not try to load OpenAPI for these sources.

So this file matters only if [choosing-a-path.md](choosing-a-path.md) sent you
to Connector.

## Where ORDS publishes specs

```
https://<host>/ords/<schema>/open-api-catalog/<module>/     # module-level
https://<host>/ords/<schema>/metadata-catalog/              # discovery index
```

A response's `links[rel=describedby]` also points at the metadata catalog entry
for that resource — a quick way to find the spec for one endpoint you already
have working.

AutoREST-enabled objects publish per-object specs. A handler-based module
publishes one spec covering its templates, which is usually the better import
because it describes the endpoints you actually designed.

## The dialect constraint

Spec type is **hardcoded** to `OPENAPI_3_0`. There is no `--spec-type` flag and
no Swagger 2.0 or OpenAPI 3.1 branch.

Modern ORDS emits OpenAPI 3.0 and imports cleanly. Older ORDS releases emit
Swagger 2.0. If yours does, convert to 3.0 before importing — the generator will
not do it, and the failure message will not mention dialect.

Check what you have:

```bash
curl -s "https://<host>/ords/<schema>/open-api-catalog/<module>/" \
  | head -c 200
```

`"openapi": "3.0.x"` imports. `"swagger": "2.0"` must be converted first.

## Size: subset before importing

The spec is read whole and posted **inline as a single JSON string in one
request**. There is no chunking, no `$ref` bundling, no operation filtering, and
no client-side size cap — a large spec either succeeds or fails server-side,
and the failure will not tell you size was the problem.

An AutoREST-enabled schema with dozens of tables produces a very large spec, and
most of it describes endpoints your agent will never call.

**Import a module, not a schema.** Prefer the handler module's spec over the
full AutoREST catalogue. If you must subset an AutoREST spec, keep only the
paths you need and the `components.schemas` they reference, then validate the
trimmed document before importing. Dropping a path while leaving a dangling
`$ref` produces a confusing server-side failure.

Fewer imported operations also means a shorter tool list for the agent to choose
from, which improves tool selection. Subsetting is a quality decision, not only
a size one.

## Two different auth questions

`--url-auth` authenticates **fetching the spec** when you pass `--spec-url`. It
is nested as `openApi: { url, urlAuth }` and has nothing to do with calls to the
API afterwards.

If your spec endpoint is protected, the simplest route is to fetch it yourself
and pass `--spec-file`, sidestepping `--url-auth` entirely.

Runtime auth is a separate problem — see [auth-on-atp.md](auth-on-atp.md).

## Failure handling

The base skill's guidance applies:

- Retry once with `--verbose`.
- Report the redacted route, resolved URL, auth mode, failure stage, and a
  curl-style command.
- If a definition id came back but detail fetch failed, **do not generate
  again** — fetch the definition by id instead. Re-running creates duplicates.

## Checklist

- [ ] Confirmed `openapi: 3.0.x`, converted if Swagger 2.0
- [ ] Importing a module spec, not a whole AutoREST schema
- [ ] Subset validated — no dangling `$ref`
- [ ] Spec fetched locally if the catalogue endpoint is protected
- [ ] Searched existing definitions before generating a new one
