Read `AGENTS.md`, `GUIDELINES.md`, `README.md`, and `docs/DEVELOPER_GUIDE.md` before changing anything.

Task: make the Windows Codex CLI preflight instructions resilient to PowerShell execution-policy errors.

Evidence: on 2026-10-27, a user ran `codex login status` in ordinary PowerShell. PowerShell selected the npm-installed `codex.ps1` shim and raised `PSSecurityException` before checking authentication. In a later shell the same account reported `Logged in using ChatGPT`, and the repository updater then completed a normal no-op run. This was an invocation-policy issue, not evidence of an authentication failure.

1. Inspect the Windows setup and updater sections in `docs/DEVELOPER_GUIDE.md` and the existing PowerShell wrappers.
2. If the guide lacks a safe, concise recovery step, update only `docs/DEVELOPER_GUIDE.md` to explain that a blocked `.ps1` shim does not establish that Codex is logged out. Document a process-scoped check such as `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "codex login status"`; state that it does not change the persistent execution policy. If that command is still blocked, tell the developer to inspect `Get-Command codex -All` and stop before changing policy or reinstalling software.
3. Keep the distinction between PowerShell script execution policy, Codex authentication, and GitHub CLI authentication clear. Do not instruct users to run `Set-ExecutionPolicy`, install/uninstall software, register scheduled tasks, or expose tokens.
4. Do not change updater code, the weekly improvement prompt, credentials, task scheduler configuration, or data files. Do not claim the fallback command was tested in Windows unless it was actually run there.
5. If an equivalent safe instruction already exists, make no change and report that result.
6. Run the repository QA checks and give a concise summary of the evidence, changed file, and any limitation.

Do not commit, push, or create a PR yourself. The isolated updater will validate the changed-path allowlist, create a candidate commit, run QA against that exact SHA, then push and open a review PR only if QA passes. Never merge or publish.
