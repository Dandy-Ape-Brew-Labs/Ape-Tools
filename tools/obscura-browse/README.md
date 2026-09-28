# obscura-browse

Browse a URL with [Obscura](https://github.com/h4ckf0r0day/obscura) — a Rust
headless browser for AI agents (V8 JS, CDP-compatible, anti-detect) — driven by
Playwright. Prints a single JSON object to stdout for easy parsing by agents.

Replaces the old `pw-obscure-test` smoke test.

## Install Obscura

```sh
tools/obscura-browse/install.sh            # stealth build (recommended)
tools/obscura-browse/install.sh --no-stealth
```

Downloads the release archive into `vendor/obscura/` (gitignored). Manual
alternative: grab a tarball from the
[releases page](https://github.com/h4ckf0r0day/obscura/releases) and put the
binary on `PATH`, or set `OBSCURA_BIN`.

## Usage

```sh
node tools/obscura-browse/browse.js <url> [options]
```

```sh
# page content as markdown (default)
node tools/obscura-browse/browse.js https://news.ycombinator.com

# raw text, plus all links
node tools/obscura-browse/browse.js https://example.com --format text --links

# extract a specific element
node tools/obscura-browse/browse.js https://example.com --selector 'h1'

# run JS in the page
node tools/obscura-browse/browse.js https://example.com --eval 'document.title'

# screenshot
node tools/obscura-browse/browse.js https://example.com --screenshot out.png
```

The tool auto-starts `obscura serve` on the CDP endpoint when it's not already
running (with `--stealth` when the binary supports it), and shuts it down on
exit. Point at an existing server with `--cdp` / `CDP_ENDPOINT`; use
`--no-server` to disable auto-start.

## Output

```json
{
  "url": "https://example.com/",
  "title": "Example Domain",
  "format": "markdown",
  "content": "# Example Domain\n\n..."
}
```

With `--eval`, the result is under `"result"`. Diagnostics go to stderr;
exit 0 on success, 1 on runtime error, 2 on usage error.

## Notes

- Obscura blocks private/loopback/LAN URLs (SSRF protection). The tool passes
  `--allow-private-network` to the server *it* starts when the target URL is
  private; a server started elsewhere needs the flag itself.
- Markdown extraction uses Obscura's `LP.getMarkdown` CDP method, falling back
  to `body.innerText`.
- Obscura also ships a standalone CLI (`vendor/obscura/obscura fetch|scrape`),
  a CDP server (`serve`), and an MCP server (`mcp`) — see `obscura --help`.
