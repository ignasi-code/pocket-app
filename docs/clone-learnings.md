# Clone Learnings

These are the lessons learned while rebuilding live-site clones in this repo.

1. Use the browser as the source of truth.
   - Inspect the live page directly before designing the clone.
   - Do not rely on memory, snippets, or old skeleton artifacts when a live DOM is available.

2. Clone the actual DOM structure.
   - Rebuild section-by-section from the live page.
   - Preserve wrapper order, spacing rhythm, hierarchy, and repeated patterns before simplifying anything.

3. Do not fall into skeleton mode.
   - A clone is not a generic approximation.
   - Placeholder cards, simplified grids, and generic shapes are only acceptable after source fidelity is already strong.

4. Verify before shipping.
   - Compare the clone against the live page in the browser.
   - Do not call the work done if the browser view still reads as a skeleton or scaffold.

5. Keep the process reusable.
   - Document the page-capture and rebuild workflow so the same process can be applied to future sites.
   - Separate source captures, clone output, and older experiments so they do not contaminate one another.

6. Commit and push the checkpoint.
   - After a meaningful clone step is complete, commit it immediately so the result is not stranded locally.
   - Push after the commit when the change should be visible in Cloudflare Pages or other shared deploys.
