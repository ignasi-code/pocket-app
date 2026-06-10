# Pocket Server Commandments

These are the rules we keep close when building storefronts, clones, and edge-first static output.

1. Browser first, always.
   - If a live page exists, inspect it in the browser before designing the clone or the data model.
   - Do not assume structure from memory, snippets, or prior guesses when the page can be observed directly.
   - Treat the browser capture as the source of truth, not a sketch or a vibe.

2. One page at a time.
   - Verify the home page, then the collection page, then the product page, then any deeper states.
   - Do not jump to a system design before the current surface is understood.

3. DOM truth beats aesthetic guesses.
   - Match the live DOM anatomy, class rhythm, content order, and interactive states first.
   - Simplify only after the source structure is locked.
   - Rebuild element-by-element from the live page; do not approximate, "inspire," or skeletonize the source when the goal is a clone.
   - If fidelity is unclear, inspect the live page again instead of guessing.

4. Reuse the source, do not redraw it.
   - Prefer direct reuse of the captured template, sections, and component structure.
   - Avoid inventing a new frontend when the source already provides the layout contract.

5. Static-first by default.
   - Keep the public output portable and easy to host on Git/Cloudflare Pages.
   - Add runtime complexity only when the static surface can no longer satisfy the requirement.

6. Edge logic is for acceleration, not ownership.
   - Use the edge for distribution, rewrites, and small dynamic helpers.
   - Do not tie the frontend too tightly to one provider unless we have explicitly accepted that tradeoff.

7. Data should be swappable.
   - Build templates so the same structure can be fed by different catalogs, products, or collections.
   - Keep content and presentation separable wherever possible.

8. Keep the first version small.
   - Start with one home, one collection, one product, cart, and checkout flow if needed.
   - Prove the shape before scaling to the full catalog.

9. Measure before expanding.
   - Optimize the first-load experience, then verify Lighthouse and real browser behavior.
   - Do not expand the catalog until the baseline is stable.

10. Preserve the important states.
    - Capture empty, populated, offline, loading, and retry flows when they matter.
    - Do not let the happy path hide critical edge cases.

11. Keep the architecture simple.
    - Favor the smallest design that gets the job done.
    - If a design adds hidden complexity, stop and challenge it before implementation.

12. Protect the lesson.
   - When we discover a better workflow, write it down in the repo immediately.
   - If a future change repeats a known mistake, treat that as a bug in the process, not just the code.

13. No fake clones.
   - Do not ship a page that only looks roughly similar if the task is to reproduce the live site.
   - Old skeleton/demo files are reference material only unless the user explicitly asks to reuse them.
   - Do not mark clone work done until the browser view is close enough that the source structure, spacing, and hierarchy are plainly the same.
