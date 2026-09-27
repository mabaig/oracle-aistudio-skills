#!/usr/bin/env node
// Run AI Studio CODE-node JavaScript locally against recorded ORDS responses.
//
// Why: CODE nodes that normalise ORDS payloads (group rows, rank, trim fields)
// are the easiest place to introduce a bug and the hardest to debug on the pod.
// This harness evaluates the node's `metadata.sourceCode` the same way the
// runtime exposes it - as a function body receiving `$context` - so you can
// iterate in seconds before saving the workflow.
//
// It is an approximation: the pod runs conservative vanilla JavaScript (no
// imports, no Intl). Keep node code to basic language features and this
// harness will behave the same.
//
// Usage
//   node code_node_harness.mjs --wf src/workflows/<wf>.wf --context ctx.json --node A [--node B ...]
//
// ctx.json is the $context the nodes should see, for example:
//   {
//     "$system": { "$currentDateTime": "2026-09-01T09:00:00Z", "$inputMessage": "" },
//     "$app":    { "$OraMessageHint": "InitDisplay", "$OraAppContext": "" },
//     "$user":   { "$name": "supervisor@example.com" },
//     "$nodes":  { "FETCH_TICKETS": { "$output": { "items": [], "hasMore": false } } }
//   }
// Put each EXTERNAL_REST node's real ORDS response (from curl or a recorded
// test) under $nodes.<CODE>.$output. Nodes passed with --node run in order;
// each result is added as $nodes.<CODE>.$output.result so later nodes can read
// it, exactly like the runtime's CODE-node output wrapper.
import fs from 'node:fs';

function arg(name, all = false) {
  const out = [];
  for (let i = 2; i < process.argv.length; i++) {
    if (process.argv[i] === name && i + 1 < process.argv.length) out.push(process.argv[++i]);
  }
  return all ? out : out[0];
}

const wfPath = arg('--wf');
const ctxPath = arg('--context');
const nodeCodes = arg('--node', true);
if (!wfPath || !ctxPath || nodeCodes.length === 0) {
  console.error('usage: node code_node_harness.mjs --wf <file.wf> --context <ctx.json> --node <CODE> [--node <CODE> ...]');
  process.exit(1);
}

const wf = JSON.parse(fs.readFileSync(wfPath, 'utf8'));
const $context = JSON.parse(fs.readFileSync(ctxPath, 'utf8'));
$context.$nodes = $context.$nodes || {};

function findNode(pipeline, code) {
  for (const node of (pipeline && pipeline.pipelineNodes) || []) {
    if (node.code === code) return node;
    const nested = findNode(node.metadata && node.metadata.dataPipeline, code);
    if (nested) return nested;
  }
  return null;
}

let failed = false;
for (const code of nodeCodes) {
  const node = findNode(wf.specification && wf.specification.dataPipeline, code);
  if (!node) { console.error(`node ${code} not found in ${wfPath}`); process.exit(1); }
  if (node.type !== 'CODE') { console.error(`node ${code} is ${node.type}, not CODE`); process.exit(1); }
  const started = Date.now();
  try {
    const result = new Function('$context', node.metadata.sourceCode)($context);
    $context.$nodes[code] = { $output: { result, timeout: false, error: null } };
    const text = JSON.stringify(result);
    console.log(`== ${code}  (${text.length} bytes, ${Date.now() - started} ms)`);
    console.log(JSON.stringify(result, null, 2));
    if (node.metadata.returnType && node.metadata.returnType !== 'object' && typeof result !== node.metadata.returnType) {
      console.warn(`WARN ${code}: returnType is ${node.metadata.returnType} but the code returned ${typeof result}`);
    }
  } catch (err) {
    failed = true;
    console.error(`== ${code} threw: ${err && err.stack ? err.stack : err}`);
    break;
  }
}
process.exit(failed ? 2 : 0);
