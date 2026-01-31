// Minimal PTY wrapper for Claude Code CLI to run under non-interactive executors.
// Spawns the given command inside a real PTY and streams output to stdout.
"use strict";

let pty;
try {
  pty = require("node-pty");
} catch (err) {
  const msg = [
    "Error: node-pty is required to run Claude Code CLI in a PTY.",
    "Install it (e.g., `npm install node-pty`) and retry.",
  ].join(" ");
  process.stderr.write(msg + "\n");
  process.exit(1);
}

const argv = process.argv.slice(2);
const cmd = argv.length > 0 ? argv[0] : "claude";
const cmdArgs = argv.length > 1 ? argv.slice(1) : [];

const cols = process.stdout.columns || 120;
const rows = process.stdout.rows || 30;

const isWin = process.platform === "win32";
const spawnCmd = isWin ? "cmd.exe" : cmd;
const spawnArgs = isWin ? ["/c", cmd, ...cmdArgs] : cmdArgs;

let term;
try {
  term = pty.spawn(spawnCmd, spawnArgs, {
    name: "xterm-256color",
    cols,
    rows,
    cwd: process.cwd(),
    env: process.env,
  });
} catch (err) {
  const detail = err && err.message ? err.message : String(err);
  process.stderr.write(`Error: failed to spawn '${cmd}': ${detail}\n`);
  process.exit(1);
}

term.onData((data) => {
  process.stdout.write(data);
});

process.stdin.on("data", (data) => {
  try {
    term.write(data);
  } catch (_) {
    // Best-effort; ignore if PTY is closed.
  }
});
process.stdin.resume();

if (process.stdout && process.stdout.isTTY) {
  process.stdout.on("resize", () => {
    try {
      const c = process.stdout.columns || cols;
      const r = process.stdout.rows || rows;
      term.resize(c, r);
    } catch (_) {
      // Best-effort.
    }
  });
}

process.on("SIGINT", () => {
  try {
    term.write("\x03");
  } catch (_) {
    // Best-effort.
  }
});

term.onExit((ev) => {
  const code = typeof ev.exitCode === "number" ? ev.exitCode : 1;
  process.exit(code);
});
