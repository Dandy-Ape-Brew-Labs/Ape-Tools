#!/usr/bin/env node
// Browse a URL with the Obscura headless browser via Playwright over CDP.
// Auto-starts `obscura serve` when the endpoint is unreachable.

import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const DEFAULT_ENDPOINT = 'ws://127.0.0.1:9222';
const SERVER_READY_TIMEOUT_MS = 15_000;
const PRIVATE_HOST = /^(localhost|0\.0\.0\.0|::1|127\.|10\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/;

const USAGE = `Usage: browse.js <url> [options]

Options:
  --format <fmt>     Output format: markdown|text|html (default: markdown)
  --links            Include all <a href> links in the output
  --eval <js>        Evaluate a JS expression in the page and output its result
  --selector <css>   Wait for a CSS selector; scopes text/html extraction to it
  --screenshot <f>   Save a full-page PNG screenshot to <f>
  --wait-until <w>   load | domcontentloaded | networkidle (default: load)
  --timeout <ms>     Navigation/extraction timeout in ms (default: 30000)
  --cdp <url>        CDP endpoint (default: $CDP_ENDPOINT or ${DEFAULT_ENDPOINT})
  --stealth          Start server with --stealth (default: on, if supported)
  --no-stealth       Disable stealth
  --no-server        Do not auto-start obscura serve; fail if endpoint is down
  -h, --help         Show this help

Output: one JSON object on stdout. Diagnostics go to stderr.
Env: CDP_ENDPOINT, OBSCURA_BIN (path to obscura binary).`;

const die = (msg, code = 1) => { console.error(`error: ${msg}`); process.exit(code); };
const log = (msg) => console.error(`browse: ${msg}`);

function parseArgs(argv) {
  const opts = {
    format: 'markdown', links: false, eval: null, selector: null,
    screenshot: null, waitUntil: 'load', timeout: 30_000,
    cdp: process.env.CDP_ENDPOINT ?? DEFAULT_ENDPOINT,
    stealth: true, server: true, url: null,
  };
  const take = (i, flag) => {
    if (i + 1 >= argv.length) die(`missing value for ${flag}`, 2);
    return argv[i + 1];
  };
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '-h': case '--help': console.log(USAGE); process.exit(0);
      case '--format': opts.format = take(i, '--format'); i++; break;
      case '--links': opts.links = true; break;
      case '--eval': opts.eval = take(i, '--eval'); i++; break;
      case '--selector': opts.selector = take(i, '--selector'); i++; break;
      case '--screenshot': opts.screenshot = take(i, '--screenshot'); i++; break;
      case '--wait-until': opts.waitUntil = take(i, '--wait-until'); i++; break;
      case '--timeout': opts.timeout = Number(take(i, '--timeout')); i++; break;
      case '--cdp': opts.cdp = take(i, '--cdp'); i++; break;
      case '--stealth': opts.stealth = true; break;
      case '--no-stealth': opts.stealth = false; break;
      case '--no-server': opts.server = false; break;
      default:
        if (argv[i].startsWith('-')) die(`unknown flag: ${argv[i]}`, 2);
        if (opts.url) die(`unexpected extra argument: ${argv[i]}`, 2);
        opts.url = argv[i];
    }
  }
  if (!opts.url) die('missing required <url>\n\n' + USAGE, 2);
  if (opts.format === 'links') { opts.format = 'text'; opts.links = true; }
  if (!['markdown', 'text', 'html'].includes(opts.format)) die(`bad --format: ${opts.format}`, 2);
  if (opts.waitUntil === 'networkidle0') opts.waitUntil = 'networkidle';
  if (!['load', 'domcontentloaded', 'networkidle', 'commit'].includes(opts.waitUntil)) {
    die(`bad --wait-until: ${opts.waitUntil}`, 2);
  }
  if (!Number.isFinite(opts.timeout) || opts.timeout <= 0) die('bad --timeout', 2);
  return opts;
}

function findObscuraBin() {
  if (process.env.OBSCURA_BIN) return process.env.OBSCURA_BIN;
  const vendored = path.join(REPO_ROOT, 'vendor', 'obscura', 'obscura');
  if (existsSync(vendored)) return vendored;
  return 'obscura';
}

const isPrivateUrl = (url) => PRIVATE_HOST.test(new URL(url).hostname);

async function endpointReady(httpBase) {
  try {
    const res = await fetch(`${httpBase}/json/version`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

async function ensureServer(opts) {
  const wsUrl = new URL(opts.cdp);
  const host = wsUrl.hostname === 'localhost' ? '127.0.0.1' : wsUrl.hostname;
  const httpBase = `http${wsUrl.protocol === 'wss:' ? 's' : ''}://${host}:${wsUrl.port || '9222'}`;
  if (await endpointReady(httpBase)) return null;
  if (!opts.server) die(`CDP endpoint not reachable at ${opts.cdp} (--no-server set)`);

  const bin = findObscuraBin();
  const args = ['serve', '--port', wsUrl.port || '9222', '--quiet'];
  const help = spawnSync(bin, ['serve', '--help'], { encoding: 'utf8' });
  if (help.error) die(`cannot run obscura binary '${bin}': ${help.error.message}`);
  if (opts.stealth && help.stdout.includes('--stealth')) args.push('--stealth');
  if (isPrivateUrl(opts.url)) args.push('--allow-private-network');

  log(`starting ${bin} ${args.join(' ')}`);
  const child = spawn(bin, args, { stdio: ['ignore', 'ignore', 'inherit'] });
  child.unref();

  const deadline = Date.now() + SERVER_READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) die(`obscura serve exited early with code ${child.exitCode}`);
    if (await endpointReady(httpBase)) { log('CDP endpoint ready'); return child; }
    await new Promise((r) => setTimeout(r, 200));
  }
  child.kill();
  die(`timed out waiting for obscura serve on ${httpBase}`);
}

async function getMarkdown(page) {
  try {
    const session = await page.context().newCDPSession(page);
    try {
      const res = await session.send('LP.getMarkdown');
      return res?.markdown ?? res?.content ?? (typeof res === 'string' ? res : null);
    } finally {
      await session.detach().catch(() => {});
    }
  } catch {
    return null;
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const server = await ensureServer(opts);
  const stopServer = () => { if (server && server.exitCode === null) server.kill('SIGTERM'); };
  process.on('SIGINT', () => { stopServer(); process.exit(130); });
  process.on('SIGTERM', () => { stopServer(); process.exit(143); });

  let browser;
  try {
    browser = await chromium.connectOverCDP({ endpointURL: opts.cdp });
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(opts.url, { waitUntil: opts.waitUntil, timeout: opts.timeout });
    if (opts.selector) {
      await page.waitForSelector(opts.selector, { timeout: opts.timeout });
    }

    const out = { url: page.url(), title: await page.title() };

    if (opts.eval !== null) {
      out.result = await page.evaluate(opts.eval);
    } else if (opts.selector) {
      const el = page.locator(opts.selector).first();
      out.format = opts.format;
      out.content = opts.format === 'html' ? await el.innerHTML() : await el.innerText();
    } else {
      out.format = opts.format;
      if (opts.format === 'markdown') {
        out.content = (await getMarkdown(page)) ?? await page.locator('body').innerText();
      } else if (opts.format === 'html') {
        out.content = await page.content();
      } else {
        out.content = await page.locator('body').innerText();
      }
    }

    if (opts.links) {
      out.links = await page.$$eval('a[href]', (as) =>
        as.map((a) => ({ text: a.innerText.trim(), href: a.href })).filter((l) => l.href),
      );
    }
    if (opts.screenshot) {
      const file = path.resolve(opts.screenshot);
      await page.screenshot({ path: file, fullPage: true });
      out.screenshot = file;
    }

    console.log(JSON.stringify(out, null, 2));
  } finally {
    if (browser) await browser.close().catch(() => {});
    stopServer();
  }
}

main().catch((err) => die(err?.message ?? String(err)));
