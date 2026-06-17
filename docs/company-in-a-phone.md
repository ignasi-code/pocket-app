# Company in a Phone

## Doctrine

One Android phone should be able to run one or many small AI-managed businesses using free cloud services for public presence, intake, storage, recovery, and coordination.

The phone is not a public backend. It is the private office node.

## Control Loop

```text
iPhone ChatGPT/Codex
  -> Codex remote control
  -> Android Termux office node
  -> business workers
  -> cloud queues, inboxes, APIs, and databases
```

## Runtime Split

- **iPhone**: command screen, approvals, supervision, ChatGPT/Codex UI.
- **Android Termux**: office node, workers, sessions, account-specific scripts, local admin.
- **Cloudflare**: public edge, static sites, workers, queues, tunnels when needed.
- **GitHub**: source of truth and recovery path.
- **Supabase/Gmail/etc.**: external state and async intake.

## Rules

- Public inputs land at the edge or in cloud storage first.
- The phone pulls work; it does not expose a public backend by default.
- Each business module must run without a Mac mini.
- The Mac mini, when present, is a factory and accelerator, not a runtime dependency.
- Secrets stay in `.env` or encrypted storage and are not committed.
- Important state must be recoverable from Git or cloud services.

## Repo Structure

```text
office/
  businesses/
    maison-flou/
      README.md
      .env.example
      prompts/
      workers/
  shared/
    ai/
    email/
    queues/
    storage/
    health/
  runtime/
    termux/
    iphone/
  scripts/
```

## Recovery Rule

A business can be moved to another Android phone or temporarily run from another machine if its code, config template, queues, and cloud state are available.

Local `.env` files are intentionally excluded from Git.
