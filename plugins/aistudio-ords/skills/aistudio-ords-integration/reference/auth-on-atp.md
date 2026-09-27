# Authenticating against ORDS on ATP

This is the step that dead-ends most ORDS integrations, so read it **before**
you create a tool. The path you pick here determines whether your integration
can ever be built end to end without a human in the UI.

## The block, stated plainly

The CLI will not write credentials into an External REST or MCP tool:

> External REST tools created through the CLI must use authInfo.type "none".
> Add authentication in the UI instead.

> CLI-created External REST and MCP tools must not include credentials, secrets,
> auth headers, API keys, passwords, client secrets, private keys, or credential
> ids. Create the safe draft through CLI, then have the user add authentication
> in the UI.

This is a sound decision: it keeps secrets out of source-controlled `.tool`
files. But it has a consequence nobody documents. **An authenticated External
REST tool cannot be produced by automation alone.** There will always be a
manual UI step.

The `--credential-type`, `--credentials` and `--oauth` flags exist on tool
creation but reach **only** the MCP branch. Passing them alongside an ORDS REST
endpoint does nothing.

## Know what you are authenticating to first

Before creating anything, prove the ORDS side works from a shell:

```bash
# 1. anonymous call: 401 means the module is protected
curl -s -o /dev/null -w '%{http_code}\n' "https://<adb-host>/ords/<schema-alias>/<module-base-path>/<template>"

# 2. token exchange with the dedicated client (secret read from a git-ignored .env.local)
curl -s -u "$ORDS_CLIENT_ID:$ORDS_CLIENT_SECRET" -d grant_type=client_credentials \
     "https://<adb-host>/ords/<schema-alias>/oauth/token"

# 3. same call with the token: 200 and an items/hasMore envelope
curl -s -H "Authorization: Bearer $TOKEN" "https://<adb-host>/ords/<schema-alias>/<module-base-path>/<template>" | head -c 300
```

`scripts/ords_openapi.py probe` runs step 3 for every GET in a module spec. If
step 2 works but step 3 returns `401`/`403`, the client lacks the role the
module's privilege requires. Compare privileges and client roles with
[../assets/sql/ords-introspection.sql](../assets/sql/ords-introspection.sql).

## Route A: External REST + UI hand-off

Use when ORDS is open or IP-restricted, or when one manual step is acceptable.

1. Create the draft from the CLI. It will carry `authInfo.type = "none"`.
2. Validate it, then **save it to the pod**. The UI can only add auth to a
   tool that exists there.
3. In AI Studio, open the tool and add authentication. For ORDS use **OAuth2
   client credentials**:
   - token URL `https://<adb-host>/ords/<schema-alias>/oauth/token`
   - the dedicated client's ID and secret, typed into the UI. The secret never
     goes through the CLI, chat, or source control.
4. Set the instance URL if you left it empty at creation. It is the module base
   URL, `servers[0].url` in the spec.
5. Only now record live workflow tests.

**What this costs you.** The tool is unusable until step 3. That step cannot be
scripted, replayed in CI, or reproduced on a second pod from source alone. If
you promote across environments, budget a manual step per environment and
document it. An undocumented manual step is how a working integration becomes
a broken one after a refresh.

**How it fails if you skip step 3.** The workflow's first `EXTERNAL_REST` node
fails with ORDS's HTML error page (`<!DOCTYPE html>… <title>Unauthorized</title>`).
The test recorder reports it as *"Captured output appears to be a
backend-truncated preview"* and asks for model data for every downstream node.
That is not a data problem. Add the auth and re-record.

## Route B: Connector

Use when ORDS requires Basic or OAuth2 and you want the integration
reproducible. This is the only path where credentials are collected
programmatically.

**Precondition:** the connector and Knowledge Management APIs must answer for
your user. Run the probes in
[setup-and-preflight.md](setup-and-preflight.md#3--probe-what-your-user-can-actually-reach).
A `401` on `search-connector-definitions` while workflow commands work usually
means the IDCS public client lacks the **Oracle Boss Cloud (Spectra)** scope,
or the user lacks the connector role. Fix that, then run `authenticate` again.

The instance flow is **staged**. Do not try to collect everything at once:

> Before every `do-create-connector-instance` attempt, run
> `prepare-connector-instance-create`… Treat the single returned `nextStage` as
> authoritative. Ask only for the returned stage. Do not combine family/product,
> sync fields, required config, and optional config in one prompt.

> Generation success is only the first step; never ask for auth/config before
> prepare returns `nextStage=config`.

Handling secrets during that flow:

> For secret config, warn before collecting the value and never echo secret
> values.

In outline (get exact signatures from the base `aistudio` skill):

1. `search-connector-definitions` to reuse before generating. Note its `--limit`
   caps at 5.
2. `do-generate-connector-definition --spec-file <agent-spec.json>` if nothing
   fits. Use the subset, enriched spec, not the raw ORDS one
   ([spec-handling.md](spec-handling.md)).
3. Loop `prepare-connector-instance-create`, answering one `nextStage` at a time.
4. `do-create-connector-instance`, then `do-save-connector-instance` only on
   explicit confirmation.
5. `list-km-connectors` → `list-km-connector-tools` to discover exposed operations.
6. `do-create-connector-tool --connector-id <id> --tools <names>`.
7. A workflow `TOOL` node referencing `metadata.toolCode` and `metadata.functionName`.

Note that `--url-auth` on definition generation authenticates **fetching the
spec URL**, not calls to the API. It is nested as `openApi: { url, urlAuth }`.
Confusing these two is a common and frustrating mistake.

## ORDS-side auth options

**OAuth2 client credentials** is the usual choice for machine-to-machine.
Protect the module with a role and privilege
([../assets/example/05-protect-module.sql](../assets/example/05-protect-module.sql)),
then register **a dedicated client for AI Studio**
([../assets/sql/create-oauth-client.sql](../assets/sql/create-oauth-client.sql)):

```
POST https://<adb-host>/ords/<schema-alias>/oauth/token
grant_type=client_credentials
```

Tokens are short-lived (typically `expires_in: 3600`); the integration must
refresh. Confirm your connector configuration refreshes rather than pinning one
token. A pinned token produces an integration that works for an hour and then
fails.

Do not reuse the client an APEX, VBCS or web app already uses. A shared secret
means a rotation for one consumer breaks the other, and you cannot tell from
ORDS logs which one made a call.

**Basic auth** against a database user or an ORDS-enabled schema. Simpler, but
it sends credentials on every call and ties the integration to a DB account's
lifecycle.

**No auth**, IP-restricted or in a private endpoint. Legitimate for read-only
reporting inside a controlled network. Route A costs nothing here.

**APEX-managed roles.** If the module is protected by an APEX role, the
privilege must map to whatever principal the connector authenticates as. A
common failure is a valid token that lacks the privilege: ORDS answers `401` or
`403`, not a helpful message.

## Secret hygiene

- Keep ORDS client secrets in a git-ignored, owner-only file (`.env.local`,
  `chmod 600`) and read them from the shell. Never paste one into chat, a
  ticket, a test definition or a `.tool` file.
- If a secret has been pasted somewhere it shouldn't be, rotate it, or replace
  the client with a dedicated one.
- The OAuth client **id** is not a secret and can appear in runbooks.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401` with a token you just minted | client not granted the role behind the module's privilege |
| `403` on one template, others fine | the privilege maps to a subset of the module |
| Works in `curl`, fails from the workflow | tool still `authInfo.type = "none"`; the UI step was skipped |
| Recorder says "backend-truncated preview" and the preview starts `<!DOCTYPE html>` | the same: ORDS returned its HTML 401 page to an unauthenticated tool |
| `search-connector-definitions` / `list-km-connectors` → `401`, workflow commands fine | IDCS client missing the Oracle Boss Cloud (Spectra) scope, or no connector role |
| Auth fine, `404` | wrong `/ords/<schema-alias>/<module-base-path>/<template>` segment (alias ≠ schema name, base path ≠ module name), or the module is unpublished |
| Token works, then stops after about an hour | not refreshing; client-credentials tokens expire |

## Choosing

If the integration must be reproducible from source on a fresh pod, take Route B
and accept the staged flow. If ORDS is open, take Route A and lose nothing.
Do not take Route A for a credentialed endpoint expecting to "add auth later".
Later means a manual step forever, on every environment.
