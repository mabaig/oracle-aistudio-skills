# Testing ORDS-backed workflows

An ORDS-backed workflow has a dependency your tests cannot rely on: live
database rows that change. Record the boundary once, replay it everywhere, and
keep the rest of the graph executing.

## Record at the ORDS boundary

Record the response of each ORDS node, then replay with `--data-source file`.
Conditions, transforms, prompts, LLM and agent nodes all still execute — only
the HTTP call is replayed. That keeps tests meaningful while making them
independent of whatever is in the table today.

Recorded ORDS payloads are usually too large to store raw. Compact them, and
respect the envelope rule — see the pagination section of
[ords-response-contract.md](ords-response-contract.md). The short version:

- Trim **fields** before dropping rows.
- Keep 2–5 representative rows.
- Set `hasMore: false` and make `count` / `limit` / `offset` agree.

## Assert the path, not just the answer

The most valuable assertion on an ORDS workflow is which nodes ran. If a guard
condition inverts, or an empty-result branch starts firing on populated data,
path assertions catch it and output assertions usually do not.

**Classify every executable node.** A node in neither `mustExecute` nor
`mustNotExecute` is a gap the harness will warn about. And be careful what you
forbid: a node that runs on *every* path — a stage resolver, a router
precondition — must never appear in `mustNotExecute`. Asserting otherwise fails
every test in the workflow with a message that looks like a workflow bug:

```
Workflow reached mustNotExecute node <NODE> and paused before executing it.
```

We lost a working suite to exactly that. Verify against a real execution trace,
not against assumption.

## Empty results deserve their own test

ORDS returning `{"items": [], "count": 0, "hasMore": false}` is a normal
business outcome, not an error, and it is the case most likely to produce a
confusing agent response. Generate a model-generated data variation for the
empty collection and assert the empty-state branch runs and the alternate branch
does not.

Also worth covering: a single-row collection (many display widgets are written
assuming several), and `hasMore: true` if your workflow claims completeness.

## Judge what is flexible, assert what is fixed

Deterministic checks run first; the judge is skipped entirely if they fail. So a
brittle `contains` assertion costs you all semantic signal on that test.

- **Exact assertions** for fixed contracts: fallback messages, control results.
- **Judge rubric** for grounding: require the response to cite values from the
  replayed ORDS data and invent no identifiers. Grounding is where ORDS-backed
  agents actually fail — a plausible ticket reference that appears nowhere in
  the payload is the characteristic failure.

## Keep one live smoke run

Replay makes the suite stable, which also means it never touches the live ORDS
call. A suite can stay green while every live endpoint returns `401` because an
environment lost its UI-added authentication. After each deploy to a new
environment, each ORDS privilege change and each tool save, run every
ORDS-backed workflow once against live data and check the ORDS node's status in
the trace. See [diagnosing-ords.md](diagnosing-ords.md).

## Watch the cost

Reports carry token usage and estimated AI units per model-backed node. Baseline
the suite with a run label, then compare labelled runs when you change a prompt
or swap a model.

There is no built-in AI-unit budget enforcement — the CLI measures, it does not
gate. If you want a threshold, read `aiUnitsSummary.totalAiUnits` from the suite
report and enforce it yourself.

One trap: a suite that fails early, or whose nodes stop emitting model
information, reports **fewer** AI units. Always check `computedCases` against
`totalCases` before reading a drop as a saving.

## Checklist

- [ ] Every ORDS node recorded and replayed from file
- [ ] Compacted fixtures set `hasMore: false` with a consistent envelope
- [ ] Every executable node classified; no always-on node in `mustNotExecute`
- [ ] Empty-collection variation covered
- [ ] Judge rubric requires grounding in replayed data
- [ ] AI units baselined under a run label
- [ ] One live (not replayed) smoke run per ORDS-backed workflow after each deploy, privilege change or tool save
