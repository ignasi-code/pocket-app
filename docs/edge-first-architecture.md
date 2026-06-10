# Edge-First Pocket Spec

## Goal

Build a simple, fast system where Cloudflare serves almost everything first, the server is used only when necessary, and Git lets any machine act as a builder.

## Components

- **Cloudflare Pages**: public frontend hosting for static output.
- **Cloudflare Workers / Functions**: lightweight edge logic, cache handling, and request shaping.
- **Cloudflare storage / cache**: reusable responses, generated assets, and large files that should not live on the Termux device.
- **Termux server**: source/origin, generator, admin box, and fallback for anything that needs local files, shell, or build steps.
- **Git**: shared source of truth and transport between machines.
- **Shopify or other commerce backend**: CRM, catalog, and order management when desired.

## Rules

- If it can be static, make it static.
- If it can be cached, cache it.
- If it can live at the edge, keep it at the edge.
- If it only needs to be generated once, generate it once and reuse it.
- If the server is not required for a request, do not involve the server.
- Keep the system simple and strict.

## Storage Policy

- Cloudflare may act as both front door and storage for reusable outputs.
- Large generated files like images, exports, and videos should move off the Termux device once they are safely stored or served from Cloudflare.
- The Termux server does not need to retain every generated artifact.
- The server remains the source of truth only where a mutable or sensitive original is required.

## Frontend

- The frontend lives on Cloudflare Pages.
- The live site should be built as static output whenever possible.
- The UI should call the server only for actions that truly need it.
- The result should feel instant because most visits never reach the server.

## Server

- The server runs on Android with Termux.
- It is a scratch box, not the performance bottleneck.
- It handles backend-only work, admin actions, shell access, local filesystem work, and rare regeneration.
- It can be skipped for normal browsing when the edge cache already has the response.

## UI Factory

- The Termux server can build the UI.
- Any other computer with the same repo, Flask/tooling, and Git access can also build the UI.
- The source of truth is the code in Git, not one specific device.
- Any machine can pull, build, test, and export the static site.

## Storefront Split

- `/store` is a static storefront surface.
- The server builds the UI, but Cloudflare Pages serves the deployed result from the `dist/` output.
- Shopify can act as CRM, catalog, media host, and order manager.
- Some images or videos can stay on Shopify CDN if that is the best fit.
- Other assets can live in Cloudflare-backed storage or cache.
- Checkout is replaceable.
- The storefront can send checkout to Shopify, Stripe, or another provider while still syncing orders back into Shopify if desired.

## When the Server Is Used

- Generating or refreshing data.
- Building or exporting static frontend output.
- Running admin actions.
- Handling local shell or filesystem work.
- Filling cache misses or stale entries.

## What Should Not Depend On the Server

- Normal page loads.
- Reused storefront assets.
- Large generated files after they have been moved to Cloudflare.
- Any request that can be answered from the edge.

## Practical Workflow

1. Edit code on any machine.
2. Pull and build from Git.
3. Generate static output or reusable artifacts.
4. Push the result to Cloudflare Pages, cache, or storage.
5. Let the edge serve it until something changes.

## Summary

Cloudflare is the fast front door, the memory, and often the storage. The Termux server is the generator and fallback. Git keeps every machine equal. The frontend stays instant by staying strict.

## Decision Note

- One build.
- Cloudflare is the primary host.
- Backup hosts can serve the same static build.
- Edge-only features should fail softly in JS.
- Termux is for backend and admin work, not the normal fallback path.
- Cloudflare Functions/Workers are the default fallback layer for edge-only flows.
