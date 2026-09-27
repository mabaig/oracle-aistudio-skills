# Worked example — service desk on ORDS

A deliberately tiny ORDS module for walking the six steps in `SKILL.md` end to
end on a clean pod.

| File | What it is |
|---|---|
| `01-schema.sql` | Two tables and five rows |
| `02-ords-module.sql` | Handler-based ORDS module, three endpoints |
| `03-sample-responses.json` | What each endpoint actually returns |
| `04-tool-endpoints.json` | Endpoint blocks for the External REST path (resource paths relative to `https://<host>/ords/<schema-alias>`) |
| `05-openapi-module.json` | Sample of the OpenAPI document ORDS serves at `/open-api-catalog/servicedesk/` — use it to try `scripts/ords_catalog.py` offline |

## Why handlers instead of AutoREST

AutoREST on `tickets` would expose all eight columns including `id` and
`queue_id`, and force a second call to resolve the queue name. The handler joins
once and returns the seven fields an agent needs. That is the whole argument for
trimming in SQL rather than in the workflow.

## Three shapes in one module — on purpose

- `/tickets` — enveloped collection with `links`
- `/tickets/:reference` — enveloped, single item
- `/summary` — **no envelope**, a bare JSON object

If you model this module correctly you have met every shape ORDS produces.

## Suggested path

The module has no authentication, so the **External REST** path is the least
work — the CLI's `authInfo.type = "none"` restriction costs you nothing here.
To practise the Connector flow instead, enable OAuth2 on the module first and
read `reference/auth-on-atp.md`.

## Walk it through

[reference/end-to-end-walkthrough.md](../../reference/end-to-end-walkthrough.md)
takes this module from DDL to a tested app panel, step by step.

Offline, without a database:

```bash
python3 ../../scripts/ords_catalog.py endpoints 05-openapi-module.json
python3 ../../scripts/ords_catalog.py subset 05-openapi-module.json --paths /summary -o summary-only.json
```

## Try the empty case

`GET /servicedesk/tickets?status=ARCHIVED` returns an empty collection. Build a
test for it. It is the case most likely to produce a confusing agent response
and the one most often left untested.
