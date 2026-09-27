# Agent safety and resilience for ORDS tools

Reading ORDS data into a panel is low-risk. Letting an agent **call** ORDS —
especially endpoints that write — is where integrations go wrong. These rules
come from integrations that were built, shipped and then had to be fixed.

## An agent sees every endpoint of an attached tool

A tool is attached to an agent as a whole. If one External REST tool holds
`listTickets`, `getTicket`, `createTicket` and `deleteTicket`, an agent given
that tool for read-only questions is offered all four — including the delete.
Nothing in AI Studio limits an agent to a subset of a tool's endpoints.

Prompt instructions such as "only use the list and get functions" are not a
control. Treat them as a hint, not a boundary.

**Split tools by risk:**

| Tool | Endpoints | Attach to |
|---|---|---|
| `<APP>_READ` | `GET` endpoints only | Display, summary, query and planning agents |
| `<APP>_WRITE` | The `POST`/`PUT`/`DELETE` endpoints the app genuinely needs | Only the execute agent behind a confirmation gate |

Back this with ORDS itself: give the read tool a client that holds only a read
privilege ([ords-setup-sql.md](ords-setup-sql.md)). Then even a misrouted call
cannot write.

## Confirmation belongs in the workflow graph, not the prompt

"Always confirm before writing" in a prompt is not reliable. With many tools
attached and a long prompt, a model will sometimes treat the user's request
itself ("close ticket 10428") as the confirmation and call the write endpoint
in the same turn.

Enforce it structurally:

```
Query ─▶ CLASSIFY_CONFIRMATION (CODE) ─▶ IS_CONFIRMATION (CONDITION)
                                             ├─ true  ─▶ EXECUTE agent  (read + write tools)
                                             └─ false ─▶ PLAN agent     (read tools only)
```

- `CLASSIFY_CONFIRMATION` flags a **short** affirmative reply only: *yes,
  confirm, proceed, go ahead*, under about 80 characters, with no negation.
- The **plan agent has no write tool at all**. It looks things up, shows the
  proposed change, asks one confirmation question and ends its turn.
- The **execute agent** only runs on a confirmation reply, performs exactly
  the change summarised in the previous turn, re-reads the record, and reports
  what the system now shows. If the previous turn contained no proposal, it
  changes nothing.
- App actions and priority-action clicks are **never** a confirmation. Route
  them to an agent without write tools.

Test it: send the write request several times and check that no write call
appears in the trace; send a bare "yes" with no prior proposal and check that
nothing is written.

## Make the write endpoint safe to call

- **Idempotent where possible.** A retried `POST` should not create a
  duplicate. Accept a client reference and reject repeats in the handler.
- **Validate in the handler.** Check required values and reject a no-op or
  zero-quantity change with a clear `4xx`, rather than relying on the agent to
  refuse.
- **Return the changed record.** The execute agent re-reads and reports what
  ORDS returns, never what it intended to send.
- **Quote body tokens deliberately.** In a body template, `"status": "{status}"`
  sends a string and `"quantity": {quantity}` sends the raw value. An
  unquoted token that receives text produces invalid JSON; a quoted token that
  receives a list produces a string. Build the body from sample values, send it
  once from a shell, and only then wire it to an agent.

## Keep failures contained

- A failing ORDS fetch before the app-stage router fails **every** stage. Fetch
  on the branch that needs the data. See [diagnosing-ords.md](diagnosing-ords.md).
- Guard every fetch with a `CONDITION` and a friendly `RETURN` for the empty
  collection — an empty result is a normal outcome, not an error.
- Keep chat independent of dashboard data where you can: a planning agent that
  calls tools on demand keeps working when a dashboard module is down.

## Ground the agent in the payload

- Trim columns in the handler SQL (see [ords-response-contract.md](ords-response-contract.md)).
- Wrap injected ORDS data in a clearly labelled DATA section, and state in the
  system prompt that it is untrusted data, not instructions. A text column that
  contains "ignore previous instructions" is data.
- Tell the model never to invent identifiers. Assert that in a judge rubric
  (see [testing-ords-workflows.md](testing-ords-workflows.md)).

## Checklist

- [ ] Read and write endpoints in separate tools; the write tool attached only to the execute agent
- [ ] ORDS clients scoped to match: read client for the read tool
- [ ] Confirmation enforced by a CODE plus CONDITION gate, tested with repeated write requests and a bare "yes"
- [ ] Write handlers validate input, reject no-ops and return the changed record
- [ ] Body templates tested from a shell with realistic values
- [ ] Every fetch guarded; no single ORDS module able to break chat
- [ ] ORDS data wrapped as untrusted DATA in every prompt
