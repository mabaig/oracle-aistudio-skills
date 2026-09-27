# Testing ORDS-backed workflows

An ORDS-backed workflow has a dependency your tests cannot rely on: live
database rows that change. Record the boundary once, replay it everywhere, and
keep the rest of the graph executing.

## Preconditions for live recording

Recording runs the workflow on the pod through the debug API, so everything the
path touches must exist there and work:

1. The workflow is saved as a **remote DRAFT**. The base skill's test flow saves
   and normalises it before recording.
2. Every tool the path calls is **saved to the pod**.
3. **Authenticated tools have their auth added in the UI.** On the External
   REST path this is the manual step from [auth-on-atp.md](auth-on-atp.md);
   until it is done, nothing records.

Check the ORDS side with `curl` first. If the token exchange or the probe fails
from your shell, it will fail from the pod too.

## Test the CODE nodes before the pod does

Most ORDS workflow bugs live in the CODE node that normalises responses. Run it
locally against real responses (from `curl` or `probe`) before saving:

```bash
node <skill-dir>/scripts/code_node_harness.mjs \
  --wf src/workflows/<workflow>.wf --context ctx.json \
  --node RESOLVE_CONTEXT --node BUILD_SNAPSHOT
```

`ctx.json` holds `$system`, `$app`, `$user` and `$nodes.<FETCH_NODE>.$output`
set to real ORDS JSON. The harness runs the nodes in order, the way the runtime
wraps CODE output (`$output.result`), and prints each result and its size. Use
it to check grouping, ranking, trimming and payload size (stay well under what
you want an LLM to read), and to confirm the node needs no `Intl` or other
unsupported APIs.

## Record at the ORDS boundary

Record the response of each ORDS node, then replay with `--data-source file`.
Conditions, transforms, prompts, LLM and agent nodes all still execute; only
the HTTP call is replayed. That keeps tests meaningful while making them
independent of whatever is in the table today.

Recorded ORDS payloads are usually too large to store raw. Compact them, and
respect the envelope rule; see the pagination section of
[ords-response-contract.md](ords-response-contract.md). In short:

- Trim **fields** before dropping rows.
- Keep 2–5 representative rows.
- Set `hasMore: false` and make `count` / `limit` / `offset` agree.

For app-backed workflows whose stages share the same fetches (the recommended
topology: shared fetches → snapshot CODE → stage router), record **InitDisplay**
once as the baseline and let the other stages (InitActions, Query, Summary)
replay it. Do not record each stage separately.

## Read recording failures correctly

| What the recorder says | What actually happened | Do this |
|---|---|---|
| "Captured output appears to be a backend-truncated preview ending with ....." on the **first** ORDS node, and the run preview contains `<!DOCTYPE html>` / `Unauthorized` | ORDS returned its HTML 401 page; the tool has no auth | add auth to the tool in the UI, then re-record |
| "Debug run did not capture output for replayed EXTERNAL_REST node …" on every node **after** the first | the run stopped at the first failure; these nodes never executed | fix the first node; do not fabricate data for the rest |
| truncated preview on a node that returned `200` | the response is over the ~3 KB capture budget | compact per the rules above, keep `capture.mode = "model-compacted"` |
| `404` HTML page | wrong alias, base path or template in the tool's instance URL or resource path | compare with the catalog `canonical` link and `servers[0].url` |

Do not replace a failed representative recording with model-generated data to
"get past" an auth or URL problem. The test would pass against data the
integration has never actually fetched.

## Assert the path, not just the answer

The most valuable assertion on an ORDS workflow is which nodes ran. If a guard
condition inverts, or an empty-result branch starts firing on populated data,
path assertions catch it and output assertions usually do not.

**Classify every executable node.** A node in neither `mustExecute` nor
`mustNotExecute` is a gap the harness will warn about. And be careful what you
forbid: a node that runs on *every* path, such as a stage resolver or a router
precondition, must never appear in `mustNotExecute`. Asserting otherwise fails
every test in the workflow with a message that looks like a workflow bug:

```
Workflow reached mustNotExecute node <NODE> and paused before executing it.
```

We lost a working suite to exactly that. Verify against a real execution trace,
not against assumption.

**Panel routing.** When one workflow serves several app panels and routes
InitDisplay on `$context.$app.$OraAppDisplayDiscriminator`, the test input
carries no discriminator. The recorded InitDisplay therefore runs your
**default** (false/else) branch, whatever the sync plan predicted from topology.
Make the most important panel the default branch, and refine path assertions
from the observed run.

## Empty results deserve their own test

ORDS returning `{"items": [], "count": 0, "hasMore": false}` is a normal
business outcome, not an error, and it is the case most likely to produce a
confusing agent response. Generate a baseline-derived variation that overrides
the fetch with the empty collection, and assert the empty-state branch or
widget runs and the alternate does not.

Also worth covering: a single-row collection (many display widgets are written
assuming several), and `hasMore: true` if your workflow claims completeness.

## Writes are real

A live recording of an InvokeAction or other write path **executes the write**
against ORDS. The test sync plan schedules one representative InvokeAction
recording by default. Run it against non-production data or a record created
for the purpose, and cover rejection paths with baseline overrides instead of
live writes. See [write-back-actions.md](write-back-actions.md).

## Judge what is flexible, assert what is fixed

Deterministic checks run first; the judge is skipped entirely if they fail. So a
brittle `contains` assertion costs you all semantic signal on that test.

- **Exact assertions** for fixed contracts: fallback messages, control results.
- **Judge rubric** for grounding: require the response to cite values from the
  replayed ORDS data and invent no identifiers. Grounding is where ORDS-backed
  agents actually fail. A plausible case number that appears nowhere in the
  payload is the characteristic failure.

## Watch the cost

Reports carry token usage and estimated AI units per model-backed node. Baseline
the suite with a run label, then compare labelled runs when you change a prompt
or swap a model.

There is no built-in AI-unit budget enforcement; the CLI measures, it does not
gate. If you want a threshold, read `aiUnitsSummary.totalAiUnits` from the suite
report and enforce it yourself.

One trap: a suite that fails early, or whose nodes stop emitting model
information, reports **fewer** AI units. Always check `computedCases` against
`totalCases` before reading a drop as a saving.

## Checklist

- [ ] Workflow and tools saved to the pod; UI auth added on authenticated tools
- [ ] CODE nodes run locally against real ORDS responses
- [ ] Every ORDS node recorded and replayed from file; stages share one InitDisplay baseline
- [ ] Compacted fixtures set `hasMore: false` with a consistent envelope
- [ ] Every executable node classified; no always-on node in `mustNotExecute`
- [ ] Default panel branch is the one the recorded InitDisplay exercises
- [ ] Empty-collection variation covered
- [ ] Write-path recording pointed at non-production data
- [ ] Judge rubric requires grounding in replayed data
- [ ] AI units baselined under a run label
