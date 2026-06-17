# Termux Runtime

The Android phone is the office node.

Expected local capabilities:

- `sshd` for emergency/admin access
- `codex-termux` wrapper for Codex CLI on Termux
- `python` for workers
- `git` for source sync
- `termux-wake-lock` for long-running work
- Tailscale as backup private access

Current proven control path:

```text
iPhone Codex -> Codex remote control -> Termux Codex app-server
```
