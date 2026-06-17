# Maison Flou

Maison Flou is the first Company-in-a-Phone business module.

Initial responsibilities:

- public static brand surface
- waitlist/intake handling
- content generation workflows
- social publishing workflows
- lead/customer state sync
- daily autonomous office loop

This module should run on the Termux office node without depending on the Mac mini.

## Local config

Shared credentials live in the root `.env`, especially `BUFFER_API_KEY`.
Business-owned routing lives in `office/businesses/maison-flou/.env`:

- `BUFFER_ORGANIZATION_ID`
- `BUFFER_CHANNEL_ID`
- `BUFFER_DEFAULT_MODE`
- `BUFFER_METADATA_SERVICE`
- `BUFFER_POST_TYPE`

API calls can select this module with `business=maison-flou`.
