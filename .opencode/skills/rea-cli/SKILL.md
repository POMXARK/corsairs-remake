---
name: rea-cli
description: Reverse-engineer native PE, Go/Rust, .NET, SQLite, and JS/ASAR targets with the REA CLI (npx rea-agents) instead of MCP. Use when a claim depends on a shipped binary's decompilation, strings, xrefs, or metadata and REA MCP tools are not in the session. Context-lean one-shot commands with file-based evidence. Skip for ordinary source-repository analysis.
---

# REA CLI (no MCP)

Use this when a claim depends on a shipped binary/package and REA MCP tools
are absent or disabled. Each CLI invocation is a separate process; there is no
session state between calls. Snapshots (`--snapshot`) are the only persistence
mechanism.

## Invocation

Pin the version matching the project's registration:

```powershell
cmd /c "npx -y rea-agents@6.7.0 <command> --json > C:\temp\opencode\<name>.json"
```

- Use `cmd /c` for redirection: PowerShell 5.1's `>` re-encodes output as
  UTF-16 (BOM), which breaks JSON consumers. `cmd /c` passes raw bytes
  through, keeping the file valid UTF-8.
- Default output is TOON; always use `--json` when saving to a file.
  Redirected `--json` is compact (smaller for agents).
- Output paging: `--token-limit N`, `--token-offset N`.
- Exit codes: `0` completed (may include partial evidence/warnings),
  `1` failed, `128+N` signal-derived.

## Context rules (mandatory)

1. Never let a full result print to the transcript. Redirect every `--json`
   result into `C:\temp\opencode\` and read it with offset/limit or project
   the needed fields first.
2. Reuse work with snapshots: pass the same `--snapshot <path>` on repeated
   queries; exact matches (target bytes, operation, parameters, provider,
   settings) are served from the file without restarting the provider.
3. For large saved Evidence, page it instead of reading it: wrap the evidence
   in a view file and run `rea inspect-analysis-view` with
   `{"kind": "summary"}` or `{"kind": "page", "collection": ..., "offset": 0,
   "limit": 32}`.
4. Diagnose only when blocked. Do not run doctor before every command.

## Native PE via Ghidra (primary workflow)

This machine: Ghidra 12.1.4 at
`C:\Users\User\AppData\Local\ghidra_12.1.4\ghidra_12.1.4_PUBLIC`, JDK 21 at
`C:\Users\User\AppData\Local\jdk-21\jdk-21.0.12.1+1`. Windows Ghidra P0 is
read-only and accepts x86 / x86-64 / ARM PE applications and DLLs on local
NTFS volumes.

Set the environment for every command (same bash-tool invocation). REA
requires Node 22.x (>=22.19), 24.x (>=24.11), or 26+; this machine's default
is Node 20, so prepend the nvm v22 path:

```powershell
$env:Path = "C:\Users\User\AppData\Roaming\nvm\v22.22.3;" + $env:Path
$env:GHIDRA_INSTALL_DIR = "C:\Users\User\AppData\Local\ghidra_12.1.4\ghidra_12.1.4_PUBLIC"
$env:JAVA_HOME = "C:\Users\User\AppData\Local\jdk-21\jdk-21.0.12.1+1"
```

Snapshot convention: `C:\temp\opencode\rea-snapshots\<target>.json`.

```powershell
# Overview (first call imports the binary; slow). Reuse the snapshot after.
npx -y rea-agents@6.7.0 analyze C:\path\target.exe --provider ghidra --snapshot C:\temp\opencode\rea-snapshots\target.json --json > C:\temp\opencode\rea-analyze.json

# String search
npx -y rea-agents@6.7.0 search C:\path\target.exe "text" --provider ghidra --snapshot C:\temp\opencode\rea-snapshots\target.json --json > C:\temp\opencode\rea-search.json

# Function dossier by name
npx -y rea-agents@6.7.0 function C:\path\target.exe main --provider ghidra --snapshot C:\temp\opencode\rea-snapshots\target.json --json > C:\temp\opencode\rea-function.json

# Pseudocode at an address
npx -y rea-agents@6.7.0 decompile C:\path\target.exe 0x1000 --provider ghidra --snapshot C:\temp\opencode\rea-snapshots\target.json --json > C:\temp\opencode\rea-decompile.json

# Cross-references to an address
npx -y rea-agents@6.7.0 xrefs C:\path\target.exe 0x1000 --provider ghidra --snapshot C:\temp\opencode\rea-snapshots\target.json --json > C:\temp\opencode\rea-xrefs.json

# Feature trace from a search hit
npx -y rea-agents@6.7.0 trace C:\path\target.exe "search" --provider ghidra --snapshot C:\temp\opencode\rea-snapshots\target.json --json > C:\temp\opencode\rea-trace.json
```

`instructions` returns assembly only. If a native query fails or the provider
is unavailable, run `npx -y rea-agents@6.7.0 doctor --provider ghidra --json`
and follow its remediation; do not install software without approval.
`rea providers --json` / `rea capabilities --json` list what is available;
`REA_ANALYSIS_PROVIDER` sets a standing provider preference, explicit
`--provider` overrides it.

## Other targets (no native engine needed)

```powershell
npx -y rea-agents@6.7.0 inspect-go-binary C:\path\prog --json > out.json        # Go build metadata
npx -y rea-agents@6.7.0 inspect-rust-binary C:\path\prog --json > out.json      # Rust dep list (.dep-v0)
npx -y rea-agents@6.7.0 inspect-managed-artifact C:\path\A.dll --json > out.json  # .NET identity/deployment
npx -y rea-agents@6.7.0 inspect-managed-members C:\path\A.dll --type X.Y --json > out.json
npx -y rea-agents@6.7.0 inspect-sqlite-database C:\path\db.sqlite --table t --row-limit 20 --json > out.json
npx -y rea-agents@6.7.0 analyze-javascript-application C:\path\app --json > out.json  # JS dir/ASAR
```

Choose the workflow from artifact contents, not extension: the managed parser
needs PE/CLI metadata and does not unpack .NET single-file hosts or decode
IL2CPP; those need native analysis.

## Evidence tools

```powershell
npx -y rea-agents@6.7.0 evidence-import bundle.json
npx -y rea-agents@6.7.0 evidence-export bundle.json canonical.json
npx -y rea-agents@6.7.0 compare left.json right.json
```

## Windows caveats

- `import-reference-source` returns `unsupported_host` on native Windows; use
  WSL/Linux if source-to-bundle comparison is required.
- Windows Ghidra P0 is read-only: no annotation/renaming through REA.
- If one-shot analysis fails and closing the session also fails, both errors
  are reported; captured output and partial observations remain in the
  original details.
