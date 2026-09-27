# ORDS URLs and the OpenAPI catalog

Every ORDS integration starts with two questions: *what is the exact URL of each
endpoint*, and *where is the machine-readable description of it*. Get these
right before you author any tool — a wrong segment produces a `404` that looks
like an auth or deployment problem.

All hosts, schemas and modules below are placeholders. Substitute your own.

## URL anatomy

```
https://<host>/ords/<schema-alias>/<module-base-path><template-pattern>
└──── host ───┘└ ORDS ┘└─ schema ─┘└──── module ────┘└─── template ───┘
```

| Segment | Where it comes from | Example |
|---|---|---|
| `<host>` | The database's ORDS host. On Autonomous Database it looks like `<unique-id>-<dbname>.adb.<region>.oraclecloudapps.com` (copy it from the ADB console, *Database actions → View all database actions*, or *Tool configuration*) | `abc123-mydb.adb.us-ashburn-1.oraclecloudapps.com` |
| `/ords` | Fixed context root | `/ords` |
| `<schema-alias>` | `p_url_mapping_pattern` given to `ORDS.ENABLE_SCHEMA` — **not necessarily the schema name**. Defaults to the lower-cased schema name | `/sdesk` |
| `<module-base-path>` | `p_base_path` given to `ORDS.DEFINE_MODULE`, with its trailing slash | `/servicedesk/` |
| `<template-pattern>` | `p_pattern` given to `ORDS.DEFINE_TEMPLATE`. Path parameters are written `:name` | `tickets/:reference` |

Putting it together:

```
https://abc123-mydb.adb.us-ashburn-1.oraclecloudapps.com/ords/sdesk/servicedesk/tickets/:reference
```

Look the values up rather than guessing them — see
[ords-setup-sql.md](ords-setup-sql.md) for inventory queries against the
`USER_ORDS_*` views, or use the catalogs below.

## Mapping to an AI Studio External REST tool

Split the URL at the schema alias:

| AI Studio field | Value | Example |
|---|---|---|
| Instance URL | `https://<host>/ords/<schema-alias>` — no trailing slash | `https://abc123-mydb.adb.us-ashburn-1.oraclecloudapps.com/ords/sdesk` |
| Endpoint `resourcePath` | `/<module-base-path><template-pattern>` with every `:name` rewritten as `{name}` | `/servicedesk/tickets/{reference}` |

Rules that save a round trip:

- **Rewrite `:name` to `{name}`.** ORDS writes path parameters as `:name`; AI
  Studio extracts tokens written as `{name}` from the resource path, headers and
  body template. A literal `:reference` in a resource path is sent as-is and
  returns `404`.
- **Query parameters.** Either put them in the resource path as tokens
  (`/servicedesk/tickets?status={status}`) or declare them as parameter
  definitions. Which parameter fields exist, and how they are sent, is owned by
  the base `aistudio` skill — read it before authoring. Keep `limit` and
  `offset` visible either way (see [ords-response-contract.md](ords-response-contract.md)).
- **Do not copy Fusion REST conventions.** `onlyData`, `fields=` and
  `expand=` belong to Oracle Fusion's REST framework, not ORDS. ORDS ignores or
  rejects them.
- **No secrets in the URL.** Never place a token, API key or password in the
  instance URL, resource path or a query parameter. Auth belongs in the tool's
  authentication settings — see [auth-on-atp.md](auth-on-atp.md).

## The two catalogs ORDS publishes

| Catalog | URL | What you get |
|---|---|---|
| **OpenAPI catalog** | `https://<host>/ords/<schema-alias>/open-api-catalog/` | An index of the schema's modules and REST-enabled objects, each with a link to its OpenAPI document |
| **OpenAPI document** | `https://<host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/` | An OpenAPI description of one module (all its templates and handlers) — the document you import on the Connector path |
| **Metadata catalog** | `https://<host>/ords/<schema-alias>/metadata-catalog/` | A discovery index of resources and their shapes |
| **Metadata entry** | `https://<host>/ords/<schema-alias>/metadata-catalog/<module-base-path><template-pattern>` | Metadata for one resource — the same URL a response's `links[rel=describedby]` points to |

Use the module-level OpenAPI document, not the whole schema: it describes the
endpoints you designed, and it is small enough to import. See
[spec-handling.md](spec-handling.md) for why size matters.

## Accessing the catalogs

### Unprotected schema or module

```bash
BASE="https://<host>/ords/<schema-alias>"

# 1. What modules and objects are published?
curl -s "$BASE/open-api-catalog/" | python3 -m json.tool | head -60

# 2. Fetch one module's OpenAPI document
curl -s "$BASE/open-api-catalog/servicedesk/" -o servicedesk-openapi.json

# 3. Which OpenAPI dialect is it?
python3 -c "import json;d=json.load(open('servicedesk-openapi.json'));print(d.get('openapi') or 'swagger '+str(d.get('swagger')))"
```

### Protected module (OAuth2 client credentials)

A module protected by an ORDS privilege protects its catalog entry too. An
anonymous request may return `401`, or an index that silently omits the
protected module. Fetch with the same token your integration will use:

```bash
# Keep the client id and secret in environment variables, never in a script.
TOKEN=$(curl -s -u "$ORDS_CLIENT_ID:$ORDS_CLIENT_SECRET" \
  -d grant_type=client_credentials "$BASE/oauth/token" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -H "Authorization: Bearer $TOKEN" "$BASE/open-api-catalog/servicedesk/" \
  -o servicedesk-openapi.json
unset TOKEN
```

The bundled helper does the same without putting the token in your shell
history — see [Helper script](#helper-script).

### What a healthy response tells you

| Request | Response | Meaning |
|---|---|---|
| `GET $BASE/metadata-catalog/` | `200` | The schema is REST-enabled and reachable; the host, alias and network path are right |
| `GET $BASE/open-api-catalog/` | `200` but your module is missing | The module is not published, or it is protected and you asked anonymously |
| `POST $BASE/oauth/token` (bad client) | `401` / `invalid_client` | OAuth2 is enabled on the schema — the client id or secret is wrong |
| `POST $BASE/oauth/token` | `404` | Wrong schema alias, or ORDS OAuth is not configured for it |

## Filtering, sorting and paging

**Paging applies to every enveloped collection:**

```
?limit=50&offset=0       # first page of 50
?limit=50&offset=50      # second page
```

Follow `hasMore` and the `next` link rather than assuming a single page. The
default page size is the module's `p_items_per_page` (25 unless set).

**Filtering depends on the resource type:**

- **AutoREST objects** accept a JSON filter object in `q`, URL-encoded:

  ```
  ?q={"status":"OPEN"}
  ?q={"priority":{"$in":["P1","P2"]},"$orderby":{"created_date":"desc"}}
  ```

  Common operators: `$eq`, `$ne`, `$lt`, `$lte`, `$gt`, `$gte`, `$like`,
  `$in`, `$null`, `$notnull`. A malformed `q` returns `400`.

- **Handler modules** read query-string values through bind variables in the
  handler SQL. `GET .../tickets?status=OPEN` binds `:status`, as in
  [the worked example](../assets/example/02-ords-module.sql). Design the
  filter parameters you want the agent to use as explicit binds; do not rely on
  `q` for handlers until you have tested it against your ORDS release.

**URL-encode values.** A literal space, `#`, `&` or `"` in a query value
breaks the URL. When a filter value comes from a workflow expression, make sure
it is encoded or restricted to safe characters.

## Helper script

[`scripts/ords_catalog.py`](../scripts/ords_catalog.py) (Python 3 standard
library only) wraps the steps above:

```bash
S=plugins/aistudio-ords/skills/aistudio-ords-integration/scripts/ords_catalog.py
BASE="https://<host>/ords/<schema-alias>"

python3 $S modules  --base "$BASE"                      # list modules in the catalog
python3 $S spec     --base "$BASE" --module servicedesk -o servicedesk-openapi.json
python3 $S endpoints servicedesk-openapi.json -o endpoints.json   # AI Studio endpoint blocks
python3 $S subset   servicedesk-openapi.json --paths /tickets /summary -o trimmed.json
python3 $S check    --base "$BASE" --path /servicedesk/tickets    # status + envelope shape
```

Add `--auth client-credentials` to any network command to fetch a token from
`$BASE/oauth/token` using `ORDS_CLIENT_ID` and `ORDS_CLIENT_SECRET` from the
environment, or `--bearer-env NAME` to read an existing token from an
environment variable. The token is held in memory and never printed.

`endpoints` output is a starting point, not a finished tool: review each
description, remove endpoints the agent must not call, and confirm the field
names against the base `aistudio` skill before creating anything.

## Checklist

- [ ] Host, schema alias, module base path and template pattern confirmed from the catalog or `USER_ORDS_*` views
- [ ] Instance URL ends at the schema alias; resource paths start with the module base path
- [ ] Every `:name` path parameter rewritten as `{name}`
- [ ] No Fusion-only query parameters (`onlyData`, `fields`, `expand`)
- [ ] OpenAPI document fetched per module, with the integration's own token if protected
- [ ] Dialect checked (`openapi: 3.0.x`) before any Connector import
- [ ] No token, key or password in any URL
