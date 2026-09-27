# Worked example: service desk on ORDS

A deliberately tiny ORDS module for walking the method in `SKILL.md` end to end
on a clean pod. Everything uses placeholders (`<adb-host>`, `<schema-alias>`);
nothing here points at a real environment.

| File | What it is |
|---|---|
| `01-schema.sql` | Two tables and five rows |
| `02-ords-module.sql` | Handler-based ORDS module, three read endpoints, all three response shapes |
| `03-sample-responses.json` | What each read endpoint actually returns |
| `04-tool-endpoints.json` | External REST endpoints, every workflow-set value a `{token}`; accepted by the CLI as-is |
| `05-protect-module.sql` | Role + privilege so the module needs OAuth2, for practising the authenticated paths |
| `06-write-handler.sql` | `POST tickets/assign` that reports real `SQL%ROWCOUNT` counts and skipped keys |
| `07-agent-openapi.json` | The agent spec after subsetting and enrichment: operationIds, real bodies, envelopes, one security scheme |
| `08-workflow-node.json` | What a normalised `EXTERNAL_REST` node for `listTickets` looks like (illustrative) |

## Run it

1. Run `01` then `02` (and `06` for the write endpoint) as an ORDS-enabled
   schema. `02` sets the schema alias to the lower-cased schema name; change
   `p_url_mapping_pattern` if you want a different URL segment.
2. Find it:

   ```bash
   python3 ../../scripts/ords_openapi.py catalog --host <adb-host> --alias <schema-alias>
   python3 ../../scripts/ords_openapi.py inventory https://<adb-host>/ords/<schema-alias>/open-api-catalog/servicedesk/
   python3 ../../scripts/ords_openapi.py probe     https://<adb-host>/ords/<schema-alias>/open-api-catalog/servicedesk/
   ```

   `inventory` flags `POST /tickets/assign` with `placeholder-body`: the
   generated spec shows `{body_text}`. Compare it with the real body documented
   in `06` and `07`.
3. Pick a path. The module is open, so **External REST** is the least work:
   create the tool from `04-tool-endpoints.json` with instance URL
   `https://<adb-host>/ords/<schema-alias>/servicedesk`.
4. To practise the authenticated flow, run `05`, create a client with
   `../sql/create-oauth-client.sql` (`servicedesk_priv` / `servicedesk_role`),
   then either import `07-agent-openapi.json` on the Connector path or save the
   External REST tool and add OAuth2 client credentials in the UI.

## Why handlers instead of AutoREST

AutoREST on `tickets` would expose all eight columns including `id` and
`queue_id`, and force a second call to resolve the queue name. The handler joins
once and returns the seven fields an agent needs. That is the whole argument for
trimming in SQL rather than in the workflow.

## Three shapes in one module, on purpose

- `/tickets`: enveloped collection with `links`
- `/tickets/:reference`: enveloped, single item
- `/summary`: **no envelope**, a bare JSON object

If you model this module correctly, you have met every shape ORDS produces.

## Try the empty case

`GET /servicedesk/tickets?status=ARCHIVED` returns an empty collection. Build a
test for it. It is the case most likely to produce a confusing agent response
and the one most often left untested.

## Try the write path safely

`POST /servicedesk/tickets/assign` with a reference that is `RESOLVED` returns
`updated_count: 0` and lists it under `skipped`. Your reporting LLM should say
nothing changed, not "assigned". Test that before trusting it with real data.
