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

This is a sound decision — it keeps secrets out of source-controlled `.tool`
files. But it has a consequence nobody documents: **an authenticated External
REST tool cannot be produced by automation alone.** There will always be a
manual UI step.

The `--credential-type`, `--credentials` and `--oauth` flags exist on tool
creation but reach **only** the MCP branch. Passing them alongside an ORDS REST
endpoint does nothing.

## Route A — External REST + UI hand-off

Use when ORDS is open or IP-restricted, or when one manual step is acceptable.

1. Create the draft from the CLI. It will carry `authInfo.type = "none"`.
2. Validate and, if the user asks, save it.
3. In AI Studio, open the tool and add authentication.
4. Set the instance URL if you left it empty at creation.
5. **Prove it with a live call.** Run the workflow against live data and read
   the ORDS node's status in the trace. Do not rely on the `.tool` file: a
   fetched tool can still read `authInfo.type: "none"` after authentication
   was added in the UI. See [diagnosing-ords.md](diagnosing-ords.md).
6. After any later CLI save of this tool, repeat step 5.

**What this costs you.** The tool is unusable until step 3. That step cannot be
scripted, replayed in CI, or reproduced on a second pod from source alone. If
you promote across environments, budget a manual step per environment and
document it — an undocumented manual step is how a working integration becomes
a broken one after a refresh.

## Route B — Connector

Use when ORDS requires Basic or OAuth2 and you want the integration
reproducible. This is the only path where credentials are collected
programmatically.

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

Broad strokes — get exact signatures from the base `aistudio` skill:

1. `search-connector-definitions` — reuse before generating. Note its `--limit`
   caps at 5.
2. `do-generate-connector-definition --spec-file <ords-spec.json>` if nothing fits.
3. Loop `prepare-connector-instance-create`, answering one `nextStage` at a time.
4. `do-create-connector-instance`, then `do-save-connector-instance` only on
   explicit confirmation.
5. `list-km-connectors` → `list-km-connector-tools` to discover exposed operations.
6. `do-create-connector-tool --connector-id <id> --tools <names>`.
7. Workflow `TOOL` node referencing `metadata.toolCode` and `metadata.functionName`.

Note that `--url-auth` on definition generation authenticates **fetching the
spec URL** — not calls to the API. It is nested as `openApi: { url, urlAuth }`.
Confusing these two is a common and frustrating mistake.

Sample SQL to create the ORDS role, privilege and OAuth client these routes
rely on is in [ords-setup-sql.md](ords-setup-sql.md).

## ORDS-side auth options

**OAuth2 client credentials** — the usual choice for machine-to-machine. Register
a client in your schema and exchange at:

```
POST https://<host>/ords/<schema>/oauth/token
grant_type=client_credentials
```

Tokens are short-lived; the integration must refresh. Confirm your connector
configuration refreshes rather than pinning one token — a pinned token produces
an integration that works for an hour and then fails.

**Basic auth** against a database user or an ORDS-enabled schema. Simpler, but
sends credentials on every call and ties the integration to a DB account's
lifecycle.

**No auth**, IP-restricted or in a private endpoint. Legitimate for read-only
reporting inside a controlled network. Route A costs nothing here.

**APEX-managed roles** — if the module is protected by an APEX role, the
privilege must map to whatever principal the connector authenticates as. A
common failure is a token that is valid but lacks the privilege: ORDS answers
`401` or `403`, not a helpful message.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401` with a token you just minted | Client not granted the ORDS privilege for that module |
| `403` on one template, others fine | Privilege maps to a subset of the module |
| Works in the UI, fails from the workflow | Tool still `authInfo.type = "none"` — the UI step was skipped |
| Auth fine, `404` | Wrong `/ords/<schema>/<module>/<template>` segment, or module not published |
| Token works then stops | Not refreshing; client-credentials tokens expire |
| Tool file says `authInfo.type: "none"` but calls succeed | Normal — the file does not show UI-added auth; prove auth by a live call |
| `555` | Not auth at all: the handler SQL raised an error |

## Choosing

If the integration must be reproducible from source on a fresh pod, take Route B
and accept the staged flow. If ORDS is open, take Route A and lose nothing.
Do not take Route A for a credentialed endpoint expecting to "add auth later" —
later means a manual step forever, on every environment.
