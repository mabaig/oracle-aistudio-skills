# Diagnosing ORDS calls from AI Studio

When an ORDS-backed panel shows nothing, or a workflow node fails, the cause is
almost always in one of four places: the URL, the ORDS privilege, the tool's
authentication, or the payload shape. Work **outside in** — prove ORDS answers
before you look at the tool, and prove the tool answers before you look at the
workflow or the app.

## Triage ladder

Run these in order and stop at the first failure. Each step takes seconds and
is decisive.

```bash
BASE="https://<host>/ords/<schema-alias>"

# 1. Is the schema REST-enabled and reachable from here?
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/metadata-catalog/"

# 2. Does the endpoint exist, and does it need auth?
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/servicedesk/tickets"

# 3. Is OAuth2 configured for the schema? (a deliberately bad client)
curl -s -o /dev/null -w "%{http_code}\n" -u bad:bad -d grant_type=client_credentials "$BASE/oauth/token"

# 4. Does the real client get a token, and does the token open the endpoint?
python3 scripts/ords_catalog.py check --base "$BASE" --path /servicedesk/tickets --auth client-credentials
```

| Step | Result | Conclusion | Next |
|---|---|---|---|
| 1 | `200` | Host, alias and network are fine | Step 2 |
| 1 | `404` | Wrong schema alias, or the schema is not REST-enabled | Check `USER_ORDS_SCHEMAS` |
| 1 | timeout / `503` | Database stopped, ORDS unavailable, or network blocked | Start the database; check access control lists |
| 2 | `200` | Endpoint is public | Auth is not the problem — go to the tool |
| 2 | `401` | Endpoint exists and is privilege-protected | Step 3 |
| 2 | `404` | Wrong module base path or template pattern, or module unpublished | Compare with [ords-url-and-catalog.md](ords-url-and-catalog.md) |
| 3 | `401` / `invalid_client` | OAuth2 is enabled; the bad client was rejected as expected | Step 4 |
| 3 | `404` | OAuth is not available at that alias | Fix the alias, or use another auth scheme |
| 4 | token, then `200` | ORDS side is correct end to end | Go to the tool |
| 4 | token, then `401`/`403` | Client lacks the role that the endpoint's privilege requires | Grant the role — see [ords-setup-sql.md](ords-setup-sql.md) |

Only when step 4 passes is it worth opening AI Studio.

## What each status code means

| Code | From ORDS it usually means |
|---|---|
| `400` | Malformed request: bad `q` filter JSON, a bind value of the wrong type, invalid JSON body |
| `401` | No credentials, or credentials ORDS does not accept for this resource |
| `403` | Authenticated, but the principal lacks the privilege mapped to this pattern |
| `404` | Nothing mapped at this path — wrong alias, base path or template, unpublished module |
| `405` | The template exists but has no handler for this HTTP method |
| `500` | ORDS internal failure; check the ORDS or database logs |
| `503` | ORDS cannot reach a database connection — the database may be stopped or the pool exhausted |
| `555` | **User-defined resource error**: the handler's SQL or PL/SQL raised an exception. The response body usually carries the ORA- error. Fix the handler, not the tool |

A `555` is easy to misread as an AI Studio or auth failure. It is almost always
a bug in the handler source, often a bind variable that arrived as `NULL` or as
text where a number was expected.

## Proving the tool, not the file

**Do not judge a tool's authentication by reading its `.tool` file.** The CLI
writes and normalises External REST tools with `authInfo.type = "none"`. A tool
whose OAuth2 was configured in the AI Studio UI can still read
`authInfo.type: "none"` after a fetch, with client id and token URL populated
beside it. The file cannot tell you whether a working credential is attached.

The only proof is a live call:

1. Run the workflow (or a one-node test workflow) against live data, not
   replayed test data.
2. Read the ORDS node's output and response status in the run trace.
3. `200` with rows → the tool works. `401` → the UI authentication step is
   missing or wrong on **this** environment.

**Treat a CLI save of a UI-authenticated tool as risky.** After any CLI save of
such a tool, repeat the live call. If `401` returns, re-check the
authentication in the UI.

## Tests pass, the app is empty

Recorded tests replay ORDS responses from file — that is their purpose — so they
never exercise the live call. A suite can stay green for weeks while every live
endpoint returns `401`. `validate-tool` and `validate-workflow` check structure,
not reachability.

Keep a separate **live smoke run** in your release routine: after deploying to a
new environment, after changing ORDS privileges, and after any tool save. One
live run per ORDS-backed workflow is enough.

## One failure takes down the whole response

A failed ORDS call inside a workflow does not degrade gracefully by default:

- A failing `EXTERNAL_REST` node on the shared path **before** the app-stage
  router fails every stage that follows it — display, actions, summary and chat.
- A tool call that returns `4xx` or `5xx` inside an agent can abort the agent's
  whole reply, not just that step.

Design for it:

- Fetch only what a stage needs. If chat answers do not need the dashboard
  fetch, keep that fetch on the display branch so a failing ORDS module cannot
  break chat.
- Put a guard `CONDITION` after each fetch and a friendly `RETURN` fallback
  for an empty or failed result.
- Where your CLI version supports a node-level error route, send failures to a
  fallback node and prove it with a forced failure. Check the base `aistudio`
  skill for the current mechanism.

See [agent-safety-and-resilience.md](agent-safety-and-resilience.md).

## Environments are not interchangeable

- Tool, workflow and app **ids differ per environment**. A tool with the same
  code on two pods is two separate records; editing one changes nothing on the
  other. Always confirm which environment the CLI and the UI are pointed at.
- **Authentication added in the UI exists only on that environment.** Budget
  and document the manual step for every environment you promote to.
- **ORDS data differs per database.** An empty panel on a test environment may
  simply be an empty table. Check row counts in ORDS before debugging the app.

## Checklist

- [ ] Triage ladder run from the outside in; first failing step identified
- [ ] `555` responses traced to the handler SQL
- [ ] Tool authentication proved by a live call, not by reading the `.tool` file
- [ ] Live smoke run after every deploy, privilege change or tool save
- [ ] Shared pre-router fetches minimised; each fetch guarded
- [ ] Environment (pod) confirmed before editing anything
