# Authoring External REST endpoints for ORDS

Use this reference when [choosing-a-path.md](choosing-a-path.md) sends you to the
External REST path. The endpoint JSON is hand-written. There is no spec import,
so every detail below is something you encode yourself. Get exact command flags
from the base `aistudio` skill; this file covers what is ORDS-specific.

## Instance URL

Set the tool's instance URL to the **module base URL**, which is the spec's
`servers[0].url`:

```
https://<adb-host>/ords/<schema-alias>/<module-base-path>
```

Each endpoint's `resourcePath` is then the template pattern, with the trailing
slash exactly as ORDS defines it. `tickets` and `tickets/` are different
templates.

## Parameters: tokens are the workflow contract

The CLI turns every `{name}` in `resourcePath`, `headers` or `bodyTemplate` into
a **token parameter** and records where it lives (`location: query | path | body | header`).
A workflow `EXTERNAL_REST` node exposes **one input per token parameter and
nothing else**. So:

- **Put every query filter the workflow must set in `resourcePath` as a token**,
  including paging:

  ```json
  { "name": "listTickets", "operationType": "GET",
    "resourcePath": "/tickets?status={status}&limit={limit}&offset={offset}" }
  ```

  A non-token `parameterDefinitions` entry cannot be bound from a workflow node.
- **Unused filters can be passed as empty strings.** ORDS binds `''` as `NULL`,
  so a handler written as `(:status IS NULL OR status = :status)` ignores it.
  Verify this once per handler with `curl`. It holds for SQL predicates, not
  necessarily for PL/SQL that calls `TO_NUMBER` or `TO_DATE` without a guard.
- **Path parameters** map one-to-one: template `tickets/:reference` becomes
  `resourcePath: "/tickets/{reference}"`.
- **Header-bound parameters** (the spec shows `in: header`) go in `headers` as
  `{ "name": "X-Ticket-Ref", "value": "{reference}" }`.
- Token values are strings. The CLI records `dataType: String` for every token
  regardless of what the ORDS column holds.

## Request bodies for PL/SQL handlers

The generated spec shows `{ "body_text": string }` for every PL/SQL handler.
Take the real shape from the handler source (see
[ords-discovery.md](ords-discovery.md#read-the-handler-source)) and write a
`bodyTemplate` with tokens:

```json
{ "name": "assignTicket", "operationType": "POST", "resourcePath": "/tickets/assign",
  "headers": [ { "name": "Content-Type", "value": "application/json" } ],
  "bodyTemplate": "{\"reference\":\"{reference}\",\"assignee\":\"{assignee}\",\"assigned_by\":\"{assigned_by}\"}" }
```

- Always send `Content-Type: application/json`. Handlers defined with
  `p_mimes_allowed => 'application/json'` reject anything else.
- For an **array** field, leave the token unquoted (`"references":{references}`)
  and pass a JSON array string such as `["TKT-1001","TKT-1004"]` from an upstream
  CODE node (`JSON.stringify(list)`). Confirm on the first live run that the
  runtime inserts the value verbatim rather than quoting it: check the handler
  response's updated count.
- **`DELETE` with a body** is legal but some clients drop the body. If a
  handler needs one, confirm the body arrives on the first live run, or expose a
  `POST …/unassign` template instead.

## Things the CLI silently changes

- `sampleQueries` supplied in the endpoint JSON may come back empty in the
  written `.tool`. Put intent into `description` instead; that is what the
  model sees.
- Parameter descriptions default to `""`. Add them with the tool update command
  if an agent (rather than a fixed workflow node) will choose the values.
- `authInfo.type` is always written as `"none"`. That is by design; see
  [auth-on-atp.md](auth-on-atp.md).

## Order of operations for an authenticated module

1. Create the tool locally, then validate it.
2. **Save the tool to the pod.** The UI can only add authentication to a tool
   that exists there.
3. In AI Studio, open the tool, add **OAuth2 client credentials**, and enter
   the token URL `https://<adb-host>/ords/<schema-alias>/oauth/token` plus the
   dedicated client's ID and secret. The secret is entered in the UI and never
   passes through the CLI.
4. Only now record live workflow tests. Before step 3, every call returns ORDS's
   HTML `401 Unauthorized` page. See the troubleshooting table in
   [testing-ords-workflows.md](testing-ords-workflows.md).
5. Repeat step 3 on every environment you promote to, and document it in the
   release notes.

## Checklist

- [ ] Instance URL is `servers[0].url`; resource paths match template patterns and trailing slashes
- [ ] Every filter, page and path value the workflow sets is a `{token}`
- [ ] Header-bound parameters are headers, not query tokens
- [ ] PL/SQL bodies come from handler source; `Content-Type` set
- [ ] Array tokens unquoted, value produced with `JSON.stringify`, verified on the first live call
- [ ] Tool saved before the UI auth step; auth step documented per environment
