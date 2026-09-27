# ORDS setup and inventory SQL (samples)

Sample SQL for the ORDS side of an integration: inventorying what already
exists, protecting a module with a privilege, and registering an OAuth2 client
for AI Studio. Run as the schema owner (or an administrator acting for it).

These are **samples**. Every name — `servicedesk`, `sdesk`,
`servicedesk_reader` — is a placeholder. ORDS PL/SQL APIs evolve between
releases; confirm each call against the documentation for your ORDS version
before running it on a shared environment. Creating modules is out of scope
for this skill; see the worked example for one.

## 1 · Inventory what exists

Start here on an existing estate. These data dictionary views describe the
current schema's ORDS objects.

```sql
-- Is the schema REST-enabled, and under which alias?
SELECT parsing_schema, pattern AS url_alias, status
  FROM user_ords_schemas;

-- Modules, base paths and page size
SELECT name, uri_prefix AS base_path, items_per_page, status
  FROM user_ords_modules
 ORDER BY name;

-- Every endpoint: module + template + method + source type
SELECT m.name        AS module,
       m.uri_prefix  AS base_path,
       t.uri_template,
       h.method,
       h.source_type
  FROM user_ords_modules   m
  JOIN user_ords_templates t ON t.module_id   = m.id
  JOIN user_ords_handlers  h ON h.template_id = t.id
 ORDER BY m.name, t.uri_template, h.method;

-- AutoREST-enabled tables and views
SELECT parsing_object, object_alias, type, status
  FROM user_ords_enabled_objects;

-- Which URL patterns are protected, and by which privilege
SELECT p.name AS privilege, pm.pattern
  FROM user_ords_privileges         p
  JOIN user_ords_privilege_mappings pm ON pm.privilege_id = p.id
 ORDER BY p.name;

-- Registered OAuth clients and their roles
SELECT c.name AS client, c.grant_type, cr.role_name
  FROM user_ords_clients      c
  LEFT JOIN user_ords_client_roles cr ON cr.client_name = c.name
 ORDER BY c.name;
```

Turn the results into the endpoint inventory that step 1 of the skill asks for.
Each row of the "every endpoint" query is one candidate tool endpoint:
`base_path || uri_template` is the resource path, with `:name` rewritten as
`{name}`. See [ords-url-and-catalog.md](ords-url-and-catalog.md).

Column names in these views can differ slightly between ORDS releases. If a
query fails, `DESCRIBE` the view.

## 2 · Protect a module with a privilege

A privilege maps a role to URL patterns. A client can call a protected pattern
only if it holds the role.

```sql
BEGIN
  ORDS.CREATE_ROLE(p_role_name => 'servicedesk_reader');

  ORDS.CREATE_PRIVILEGE(
    p_name        => 'servicedesk.read',
    p_role_name   => 'servicedesk_reader',
    p_label       => 'Service desk read',
    p_description => 'Read-only access to the servicedesk module');

  -- Protect the whole module ...
  ORDS.SET_MODULE_PRIVILEGE(
    p_module_name    => 'servicedesk',
    p_privilege_name => 'servicedesk.read');

  -- ... or protect specific patterns instead:
  -- ORDS.CREATE_PRIVILEGE_MAPPING(
  --   p_privilege_name => 'servicedesk.read',
  --   p_pattern        => '/servicedesk/tickets*');
  COMMIT;
END;
/
```

Keep **read** and **write** privileges separate. An agent integration usually
needs a read-only client; give write access to a different client, attached to
a different tool (see [agent-safety-and-resilience.md](agent-safety-and-resilience.md)).

## 3 · Register an OAuth2 client for AI Studio

Client credentials is the usual machine-to-machine grant.

```sql
BEGIN
  OAUTH.CREATE_CLIENT(
    p_name            => 'aistudio_servicedesk_reader',
    p_grant_type      => 'client_credentials',
    p_owner           => 'Service desk integration',
    p_description     => 'Fusion AI Studio read-only client',
    p_support_email   => 'integration-owner@example.com',
    p_privilege_names => 'servicedesk.read');

  OAUTH.GRANT_CLIENT_ROLE(
    p_client_name => 'aistudio_servicedesk_reader',
    p_role_name   => 'servicedesk_reader');
  COMMIT;
END;
/

-- Read the generated client id and secret ONCE, and store them in your
-- secret manager. Do not commit them, paste them in chat, or put them in a tool file.
SELECT client_id, client_secret
  FROM user_ords_clients
 WHERE name = 'aistudio_servicedesk_reader';
```

Recent ORDS releases also provide a newer security package for client
management; the `OAUTH` package calls above remain widely supported. Use
whichever your ORDS version documents as current.

## 4 · Test the client from a shell

```bash
BASE="https://<host>/ords/<schema-alias>"
# export ORDS_CLIENT_ID=... ; export ORDS_CLIENT_SECRET=...   (from your secret manager)

curl -s -u "$ORDS_CLIENT_ID:$ORDS_CLIENT_SECRET" \
     -d grant_type=client_credentials "$BASE/oauth/token"
# {"access_token":"<redacted>","token_type":"bearer","expires_in":3600}

python3 scripts/ords_catalog.py check --base "$BASE" --path /servicedesk/tickets --auth client-credentials
```

Then configure the same client on the AI Studio side:

- **Connector path:** the staged connector instance flow collects the client
  credentials.
- **External REST path:** add OAuth2 client credentials in the tool's
  authentication settings in the UI, with the token URL `$BASE/oauth/token`.

See [auth-on-atp.md](auth-on-atp.md).

## 5 · Revoke or rotate

```sql
BEGIN
  OAUTH.REVOKE_CLIENT_ROLE(
    p_client_name => 'aistudio_servicedesk_reader',
    p_role_name   => 'servicedesk_reader');
  -- OAUTH.DELETE_CLIENT(p_name => 'aistudio_servicedesk_reader');
  COMMIT;
END;
/
```

After rotating a secret, update it in AI Studio on **every** environment that
uses it, then run a live smoke test ([diagnosing-ords.md](diagnosing-ords.md)).
Recorded tests will not notice a revoked client.

## Checklist

- [ ] Endpoint inventory built from `USER_ORDS_*` (or the catalog), not from memory
- [ ] Read and write privileges and clients kept separate
- [ ] Client id and secret stored in a secret manager, never in a file or chat
- [ ] Token exchange and a protected endpoint tested from a shell before AI Studio
- [ ] Rotation procedure documented per environment
