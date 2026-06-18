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

## Maison Flou Domain Map

The apex `.com` should never depend on the phone being awake.

```text
maisonflou.com
www.maisonflou.com
  -> Cloudflare Pages
  -> static brand surface, registry/waitlist, legal/lightweight public pages

office.maisonflou.com
  -> Cloudflare Tunnel to Termux Pocket Office
  -> protected by Cloudflare Access
  -> office dashboard, setup, ops, private status, internal tools

media.maisonflou.com
  -> Cloudflare Tunnel to restricted Termux media route
  -> public read-only generated images for Buffer/social ingestion
  -> must not expose setup, ops, office, terminal, or API routes

api.maisonflou.com
  -> future Cloudflare Worker or Supabase edge function
  -> public intake only: waitlist, lead capture, webhooks, queued requests
  -> should enqueue or store work for the phone to pull later

status.maisonflou.com
  -> optional redirect/CNAME to UptimeRobot public status page
```

Initial DNS target:

```text
apex/www: Cloudflare Pages
office: protected Cloudflare Tunnel
media: public media-only tunnel once host routing is restricted in Flask
api: hold until there is a Worker/Supabase intake path
```

Do not point `maisonflou.com` or `www.maisonflou.com` at the Termux tunnel.

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

## Backlog: Office Activity Logs

Each business should keep a lightweight activity ledger so we can answer:

- what the office loop did today
- what content was generated, drafted, published, or skipped
- what external APIs were called
- what errors happened and whether they recovered
- what human approvals are waiting

The log should be business-scoped, not just system-scoped. For Maison Flou, examples include generated object number, image URL, caption, Buffer draft ID, publish status, and prompt/model metadata.

Evaluate a free hosted logging service for searchable history and alerts. Axiom was discussed as a strong candidate. Keep a local fallback log on the phone so the office can still report what happened if the external logging service is unavailable.

Future status reports should be generated from these logs, e.g. "what got done at the office today" by business and by loop.
