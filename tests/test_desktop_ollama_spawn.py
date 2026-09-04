"""U1 Rung 2 — the first run must never die on `spawn ollama ENOENT`.

Witnessed on PC-23, 2026-09-04 21:50Z, desktop-v0.2.90, first launch after a
fresh install: the wizard's consent-click Ollama installer succeeded, then the
main process crashed with a modal "A JavaScript error occurred in the main
process — Uncaught Exception: Error: spawn ollama ENOENT". Cause: after the
installer exits 0, bootstrap.ts spawned `ollama serve` by bare name — the new
install is not on the already-running process's PATH — with no 'error'
listener on the child, and Node turns an unhandled ChildProcess 'error' into an
uncaught exception. Olga's 3 September "another error popped up" is this class.

What this pins in desktop/electron/bootstrap.ts (string tests, like the rest of
the desktop suite — the TypeScript is not executed here):
  1. every ollama invocation goes through one resolver that also looks where the
     installers put the binary (Windows: %LOCALAPPDATA%\\Programs\\Ollama;
     macOS: /usr/local/bin and /opt/homebrew/bin);
  2. the post-install `serve` spawn carries an error handler and never throws;
  3. a successful Windows install prepends the Ollama directory to this
     process's PATH so the same session can see it.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO / "desktop" / "electron" / "bootstrap.ts"


def _src() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


def test_no_bare_ollama_spawn_or_exec_remains():
    src = _src()
    bare = re.findall(r'(?:spawn|execFile|execFileText|execSync)\(\s*"ollama"', src)
    assert bare == [], f"ollama invoked by bare name (PATH-dependent): {bare}"


def test_one_resolver_knows_where_the_installers_put_the_binary():
    src = _src()
    assert "function ollamaCommand(" in src, "no single resolver for the ollama binary"
    assert "process.env.LOCALAPPDATA" in src, "Windows install dir not tried"
    assert '"Programs", "Ollama"' in src
    assert '"/opt/homebrew/bin"' in src and '"/usr/local/bin"' in src
    assert "existsSync(candidate)" in src, "candidates are not checked on disk"


def test_post_install_serve_spawn_cannot_crash_the_main_process():
    src = _src()
    start = src.index("export async function installOllamaWindows(")
    block = src[start: src.index("\n}\n", start) + 3]
    serve_at = block.index('["serve"]')
    after = block[serve_at: serve_at + 600]
    assert '.on("error"' in after, "the detached `ollama serve` child has no error handler — ENOENT becomes an uncaught exception"
    assert "unref()" in after


def test_windows_install_makes_the_binary_visible_to_this_process():
    src = _src()
    start = src.index("export async function installOllamaWindows(")
    block = src[start: src.index("\n}\n", start) + 3]
    assert "addOllamaDirToPath()" in block, "the running process never learns the new install dir"
    fn = src[src.index("export function addOllamaDirToPath("): src.index("export async function checkOllama(")]
    assert "process.env.PATH" in fn
