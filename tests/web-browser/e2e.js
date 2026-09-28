#!/usr/bin/env node
// E2E test: hand each scenario's task to agent.js, then validate the agent's
// final answer against the scenario's fixed expectations. The test never
// solves the task itself — it only checks the agent's answer.

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const TOOL_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TOOL_DIR, '..', '..');
const AGENT = path.join(REPO_ROOT, 'tools', 'web-browser', 'agent.js');
const SCENARIOS = path.join(TOOL_DIR, 'scenarios.json');
const LLM_BASE_URL = (process.env.LLM_BASE_URL ?? 'http://127.0.0.1:1234/v1').replace(/\/+$/, '');
const JUDGE_MODEL = process.env.E2E_JUDGE_MODEL ?? 'qwen/qwen3-vl-8b';
const DEFAULT_TIMEOUT_S = 300;
const REPORTS_ROOT = path.join(TOOL_DIR, 'reports');

const USAGE = `Usage: e2e.js [--only <id,id,...>] [--timeout <seconds>] [--trace] [--report-dir <dir>]

Runs each scenario in scenarios.json through agent.js and validates the
answer. Every run writes a full report to <report-dir>/ (default
tests/web-browser/reports/<timestamp>/): per-scenario trace.json with every step's raw
model reply, parsed action, complete observation, and screenshot PNGs, plus
judge verdicts and the final PASSED/FAILED/UNKNOWN summary in report.json.

Exits 0 when all selected scenarios pass, 1 otherwise, 2 on setup errors
(LLM unreachable, obscura binary missing).

Env: LLM_BASE_URL, E2E_JUDGE_MODEL (model used for "judge" expectations).`;

// ---------- validation ----------

function parseAnswer(raw) {
  const cleaned = raw.replace(/```(?:json)?/g, '').trim();
  try { return { parsed: JSON.parse(cleaned) }; } catch { /* fall through */ }
  // Repair doubled quotes — a common failure when a headline itself is quoted.
  try { return { parsed: JSON.parse(cleaned.replace(/""/g, '"')) }; } catch { /* fall through */ }
  const items = cleaned.split(/[\n,]/).map((l) => l.replace(/^[\s\-*\d.)•]+/, '').trim())
    .map((l) => l.replace(/^["']|["']$/g, '').trim()).filter(Boolean);
  if (items.length >= 2) return { parsed: items };
  return { raw: cleaned };
}

function validate(answer, expect) {
  const failures = [];
  const text = typeof answer === 'string' ? answer : JSON.stringify(answer);
  const lower = text.toLowerCase();

  if (expect.format === 'json') {
    const { parsed } = parseAnswer(text);
    if (parsed === undefined) failures.push('answer is not valid JSON');
    else if (expect.minItems && Array.isArray(parsed) && parsed.length < expect.minItems) {
      failures.push(`JSON array has ${parsed.length} items, expected >= ${expect.minItems}`);
    } else if (expect.minItems && !Array.isArray(parsed)) {
      failures.push('expected a JSON array');
    }
  }
  if (expect.minItems && expect.format !== 'json') {
    const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length < expect.minItems) failures.push(`got ${lines.length} lines, expected >= ${expect.minItems}`);
  }
  for (const needle of expect.contains ?? []) {
    if (!lower.includes(needle.toLowerCase())) failures.push(`missing '${needle}'`);
  }
  if (expect.containsAny?.length) {
    const found = expect.containsAny.filter((n) => lower.includes(n.toLowerCase()));
    if (found.length < (expect.containsAnyMin ?? 1)) {
      failures.push(`matched ${found.length}/${expect.containsAnyMin ?? 1} of containsAny`);
    }
  }
  if (expect.regex && !new RegExp(expect.regex, 'i').test(text)) {
    failures.push(`regex ${expect.regex} did not match`);
  }
  if (expect.minLength && text.length < expect.minLength) {
    failures.push(`answer length ${text.length} < ${expect.minLength}`);
  }
  for (const needle of expect.notContains ?? []) {
    if (lower.includes(needle.toLowerCase())) failures.push(`contains forbidden '${needle}'`);
  }
  return failures;
}

// Semantic validation: a judge model grades the answer against the scenario's
// rubric — grading is not solving, so the test still never produces the answer.
// Grounding context (the URLs the agent visited) is included so the judge can
// flag answers disconnected from where the agent actually browsed.
const JUDGE_PROMPT = `You are grading an AI browsing agent's answer against a rubric.

TASK GIVEN TO AGENT:
__TASK__

RUBRIC:
__RUBRIC__

PAGES THE AGENT VISITED:
__SOURCES__

AGENT'S ANSWER:
__ANSWER__

Decide whether the answer satisfies the rubric. Reply with ONLY JSON:
{"pass": true, "reason": "..."} or {"pass": false, "reason": "..."}`;

async function judgeAnswer({ task, rubric, answer, sources }) {
  const prompt = JUDGE_PROMPT
    .replace('__TASK__', task)
    .replace('__RUBRIC__', rubric)
    .replace('__SOURCES__', sources.length ? sources.join('\n') : '(none recorded)')
    .replace('__ANSWER__', typeof answer === 'string' ? answer : JSON.stringify(answer));
  const raw = [];
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await fetch(`${LLM_BASE_URL}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: JUDGE_MODEL,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0,
        max_tokens: 512,
      }),
      signal: AbortSignal.timeout(120_000),
    });
    if (!res.ok) return { pass: false, reason: `judge request failed: HTTP ${res.status}`, prompt, raw };
    const text = (await res.json()).choices?.[0]?.message?.content ?? '';
    raw.push(text);
    const match = text.replace(/```(?:json)?/g, '').match(/\{[\s\S]*\}/);
    if (match) {
      try {
        const verdict = JSON.parse(match[0]);
        if (typeof verdict.pass === 'boolean') {
          return { pass: verdict.pass, reason: String(verdict.reason ?? ''), prompt, raw };
        }
      } catch { /* retry */ }
    }
  }
  return { pass: false, reason: 'judge did not return a parseable verdict', prompt, raw };
}

// ---------- scenario execution ----------

function runAgent(scenario, { timeoutS, trace, traceDir }) {
  const args = [AGENT, '--task', scenario.task, '--start-url', scenario.site,
    '--json', '--max-steps', String(scenario.maxSteps ?? 30)];
  if (trace) args.push('--trace');
  if (traceDir) args.push('--trace-dir', traceDir);
  if (scenario.model) args.push('--model', scenario.model);
  return new Promise((resolve) => {
    const child = spawn('node', args, { cwd: REPO_ROOT });
    let stdout = '', stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; if (trace) process.stderr.write(d); });
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      resolve({ ok: false, error: `timed out after ${timeoutS}s`, stderr });
    }, timeoutS * 1000);
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) resolve({ ok: false, error: `agent exited ${code}`, stderr: stderr.slice(-2000) });
      else {
        try { resolve({ ok: true, result: JSON.parse(stdout.trim()) }); }
        catch { resolve({ ok: false, error: 'agent did not emit JSON', stdout: stdout.slice(-500) }); }
      }
    });
  });
}

// ---------- preflight ----------

async function preflight() {
  try {
    const res = await fetch(`${LLM_BASE_URL}/models`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch (e) {
    die(`LLM endpoint ${LLM_BASE_URL} unreachable: ${e.message}`, 2);
  }
  const vendored = path.join(REPO_ROOT, 'vendor', 'obscura', 'obscura');
  if (!existsSync(vendored) && !process.env.OBSCURA_BIN) {
    die('obscura binary not found — run tools/obscura-browse/install.sh first', 2);
  }
}

const die = (msg, code = 1) => { console.error(`error: ${msg}`); process.exit(code); };

// ---------- main ----------

async function main() {
  const argv = process.argv.slice(2);
  let only = null, timeoutS = DEFAULT_TIMEOUT_S, trace = false, reportDir = null;
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '-h': case '--help': console.log(USAGE); process.exit(0);
      case '--only': only = argv[++i].split(','); break;
      case '--timeout': timeoutS = Number(argv[++i]); break;
      case '--trace': trace = true; break;
      case '--report-dir': reportDir = argv[++i]; break;
      default: die(`unknown flag: ${argv[i]}`, 2);
    }
  }

  await preflight();
  const scenarios = JSON.parse(await readFile(SCENARIOS, 'utf8'));
  const selected = only ? scenarios.filter((s) => only.includes(s.id)) : scenarios;
  if (selected.length === 0) die(`no scenarios matched --only=${only}`, 2);

  if (!reportDir) reportDir = path.join(REPORTS_ROOT, new Date().toISOString().replace(/[:.]/g, '-'));
  await mkdir(reportDir, { recursive: true });
  console.log(`report dir: ${reportDir}`);

  const results = [];
  const tally = { PASSED: 0, FAILED: 0, UNKNOWN: 0 };
  for (const s of selected) {
    const started = Date.now();
    process.stdout.write(`${s.id} ... `);
    const scenarioDir = path.join(reportDir, s.id);
    const { ok, result, error, stderr } = await runAgent(s, { timeoutS, trace, traceDir: scenarioDir });
    const secs = Number(((Date.now() - started) / 1000).toFixed(0));

    const record = {
      id: s.id, site: s.site, task: s.task, expect: s.expect ?? {},
      status: 'UNKNOWN', durationS: secs, traceDir: path.relative(REPO_ROOT, scenarioDir),
    };

    if (!ok) {
      // No answer to evaluate — can't say it failed the task, only that it
      // never produced one.
      record.error = error;
      if (stderr) record.stderrTail = stderr.trim().split('\n').slice(-5);
      tally.UNKNOWN++;
      console.log(`UNKNOWN (${secs}s) — ${error}`);
    } else {
      record.agentResult = result;
      const problems = validate(result.answer, s.expect ?? {});
      if (s.expect?.judge && !problems.length) {
        const verdict = await judgeAnswer({
          task: s.task, rubric: s.expect.judge, answer: result.answer, sources: result.sources ?? [],
        });
        record.judge = { model: JUDGE_MODEL, rubric: s.expect.judge, ...verdict };
        if (!verdict.pass) problems.push(`judge: ${verdict.reason}`);
      }
      record.validationFailures = problems;
      if (problems.length) {
        record.status = 'FAILED';
        tally.FAILED++;
        console.log(`FAILED (${secs}s) — ${problems.join('; ')}`);
        console.log(`  answer: ${String(result.answer).slice(0, 300)}`);
      } else {
        record.status = 'PASSED';
        tally.PASSED++;
        console.log(`PASSED (${secs}s, ${result.steps} steps)`);
      }
    }
    results.push(record);
    await mkdir(scenarioDir, { recursive: true });
    await writeFile(path.join(scenarioDir, 'verdict.json'), JSON.stringify(record, null, 2));
  }

  const summary = { total: results.length, ...tally };
  await writeFile(path.join(reportDir, 'report.json'), JSON.stringify({
    at: new Date().toISOString(),
    llmBaseUrl: LLM_BASE_URL,
    judgeModel: JUDGE_MODEL,
    summary,
    results,
  }, null, 2));

  console.log(`\n${summary.total} scenarios: ${tally.PASSED} PASSED, ${tally.FAILED} FAILED, ${tally.UNKNOWN} UNKNOWN`);
  console.log(`report written to ${reportDir}`);
  process.exit(tally.PASSED === summary.total ? 0 : 1);
}

main().catch((e) => die(e?.message ?? String(e)));
