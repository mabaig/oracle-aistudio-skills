# Discovering an ORDS estate: URLs, the OpenAPI catalog, and handler source

Step 1 of the method is an inventory. This file shows how to build every ORDS
URL you need, how to read the OpenAPI catalog, and where the generated spec
misleads you.

## URL anatomy

Every ORDS REST call on Autonomous Database has the same five parts:

```
https://<adb-host>/ords/<schema-alias>/<module-base-path>/<template-pattern>
        └─ 1 ─────┘      └─ 2 ────────┘ └─ 3 ────────────┘ └─ 4 ──────────┘  ?<5 query>
```

| # | Part | Where it comes from | Example |
|---|---|---|---|
| 1 | ADB host | Database console → Tool configuration → ORDS URL | `<db-ocid-prefix>-<db-name>.adb.<region>.oraclecloudapps.com` |
| 2 | Schema alias | `ORDS.ENABLE_SCHEMA(p_url_mapping_pattern => ...)`. **Not necessarily the schema name** | `hr_api` for schema `HR` |
| 3 | Module base path | `ORDS.DEFINE_MODULE(p_base_path => ...)`. **Not the module name** | module `servicedesk` → base `/servicedesk/` |
| 4 | Template pattern | `ORDS.DEFINE_TEMPLATE(p_pattern => ...)`; `:name` segments are path parameters | `tickets/:reference` |
| 5 | Query | handler bind variables (`:status`), plus ORDS paging `limit` / `offset` | `?status=OPEN&limit=50&offset=0` |

The schema alias and the base path are the two parts people get wrong. A
module called `servicedesk_v2` with base path `/sd/` answers at `/ords/<alias>/sd/…`
and nowhere else. A wrong segment returns `404`, not a helpful message.

Related URLs under the same alias:

| Purpose | URL |
|---|---|
| OpenAPI catalog index (all modules) | `https://<adb-host>/ords/<schema-alias>/open-api-catalog/` |
| OpenAPI 3.0 spec for one module | `https://<adb-host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/` |
| Metadata catalog (AutoREST objects, `describedby` links) | `https://<adb-host>/ords/<schema-alias>/metadata-catalog/` |
| OAuth2 token endpoint | `https://<adb-host>/ords/<schema-alias>/oauth/token` |

## Read the catalog

The index is itself an ORDS collection:

```json
{
  "items": [
    { "name": "servicedesk",
      "links": [ { "rel": "canonical",
                   "href": "https://<adb-host>/ords/<schema-alias>/open-api-catalog/servicedesk/",
                   "mediaType": "application/openapi+json" } ] }
  ],
  "hasMore": false, "limit": 25, "offset": 0, "count": 1
}
```

- `name` is the **module name**. The `canonical` link ends in the module's
  **base path**. Follow the link rather than building it from the name.
- The spec's `servers[0].url` is the module base URL,
  `https://<adb-host>/ords/<schema-alias>/<module-base-path>`. That is the value
  for an External REST tool's instance URL.
- The catalog is often readable **without credentials** even when every
  handler is protected. Module privileges usually cover the module's URL
  pattern (for example `/servicedesk/*`), not `/open-api-catalog/*`. If yours
  returns `401`, send the same bearer token as for the API. If you don't want
  the API surface public, add `/open-api-catalog/*` to a privilege.

With the bundled helper (standard-library Python, no install):

```bash
# <skill-dir> is printed as "Base directory for this skill" when the skill loads.
# Marketplace installs live under ~/.claude/plugins/cache/oracle-aistudio/aistudio-ords/<version>/skills/aistudio-ords-integration
S=<skill-dir>/scripts
python3 $S/ords_openapi.py catalog --host <adb-host> --alias <schema-alias>
python3 $S/ords_openapi.py inventory https://<adb-host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/
```

Or by hand:

```bash
curl -s "https://<adb-host>/ords/<schema-alias>/open-api-catalog/" | python3 -m json.tool
curl -s "https://<adb-host>/ords/<schema-alias>/open-api-catalog/<module-base-path>/" -o module-spec.json
head -c 200 module-spec.json        # expect "openapi": "3.0.x"
```

## Get a token

```bash
set -a; . ./.env.local; set +a                       # ORDS_CLIENT_ID / ORDS_CLIENT_SECRET
curl -s -u "$ORDS_CLIENT_ID:$ORDS_CLIENT_SECRET" \
     -d grant_type=client_credentials \
     "https://<adb-host>/ords/<schema-alias>/oauth/token"
# {"access_token":"...","token_type":"bearer","expires_in":3600}
```

Tokens last about an hour. Anything that holds one, such as a connector, must
refresh rather than pin it.

Then probe the real response shapes and page sizes:

```bash
ORDS_CLIENT_ID=... ORDS_CLIENT_SECRET=... python3 $S/ords_openapi.py probe module-spec.json
```

`probe` calls every `GET` that needs no path parameter and prints HTTP status,
shape (`enveloped+links`, `enveloped`, `bare-object`) and the `limit` ORDS
applied. That limit is the handler's real default page size.

## What the generated spec gets wrong

ORDS generates the spec from handler metadata, not from what the handler does.
`inventory` flags each of these per operation:

| Flag | What you see | Reality | Fix |
|---|---|---|---|
| `placeholder-body` | request body `{ "body_text": string }` | a PL/SQL handler reads the raw body through `:body_text` and parses it with `JSON_VALUE`/`JSON_TABLE`, so the real contract is only in the handler source | read the handler source (below) and hand-write the body schema |
| `no-operationId` | operations without `operationId` | generated tool names are unstable and meaningless to an agent | add a verb-first `operationId` per operation |
| `implicit-params` | every bind variable typed `string`, described "Implicit parameter" | types, formats and defaults are unknown to the spec | give each one a real description (`YYYY-MM-DD`, enum values, defaults) |
| `header-params` | parameters `in: header` | the handler binds HTTP headers, for example `p_source_type => 'HEADER'` | send them as headers, not query tokens |
| `envelope-undeclared` | response schema lists `items` only | ORDS still returns `hasMore`, `count`, `limit`, `offset`, `links` | declare the envelope; see [ords-response-contract.md](ords-response-contract.md) |
| (security) | `BasicAuth`, `BearerAuth`, `OAuth2` with implicit, authorizationCode and clientCredentials flows | you use one | keep only the scheme and flow you configure (`subset --security OAuth2:clientCredentials`) |

**Default page size is per handler.** `p_items_per_page` is set per module and
can be overridden per handler, so one module commonly mixes 25, 50, 100, 500 or
more. Read the `limit` in a real response, or `ITEMS_PER_PAGE` in the views
below, and never assume 25. A `limit` query parameter above the default is
honoured, so check before relying on a large page.

**Empty query parameters bind as NULL.** Oracle treats `''` as `NULL`, so
`?status=&priority=` behaves exactly like omitting both. That applies to
handlers written as `(:status IS NULL OR status = :status)`, and it lets an
External REST endpoint declare every filter as a token and pass empty strings
for the ones a call doesn't use.

## Read the handler source

When the spec shows `placeholder-body`, or you need exact filters, page sizes or
the privilege protecting a module, query the ORDS metadata views as the
REST-enabled schema. [../assets/sql/ords-introspection.sql](../assets/sql/ords-introspection.sql)
has ready queries for:

- modules, base paths and default page sizes
- templates and handlers, with source type, method, page size and **source**
- handler parameters: header and URI binds
- privileges, the patterns and modules they protect, and their roles
- OAuth clients and the roles granted to them (never select the secret)

If the module source is in version control, patch scripts often redefine the
same handler. The **last** script to run wins, so read the highest-numbered file
that defines a template, not the first. When the deployed module may have
drifted from the repo, trust the introspection views over the scripts.

## Inventory checklist

- [ ] Catalog index read; spec URL taken from the `canonical` link, not built from the module name
- [ ] `servers[0].url` noted as the instance URL
- [ ] Per operation: method, path, auth, real default page size, response shape
- [ ] Every `placeholder-body` operation has its real JSON body from handler source
- [ ] Header-bound parameters identified
- [ ] Operations the agent does not need are listed for exclusion
