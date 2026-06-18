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

Generated image files are stored locally under the ignored business runtime
folder and exposed through `/media/maison-flou/<filename>` for Buffer ingestion.
The default publishable image is a center-cropped square JPEG derivative of the
original Gemini image. The square derivative is produced from a fresh RGB pixel
canvas before JPEG encoding, mirroring a screenshot-style copy instead of
carrying source image metadata forward.

## Content mix

The creative prompt stays deliberately minimal. Product-category direction lives
in `prompts/object-categories.json` so the office can steer the generated grid
toward a reference-brand mix without hardcoding one object type into every
prompt. Successful generated objects write an ignored runtime category history
file, which lets the selector reduce recent repetition and support future office
activity reports.
