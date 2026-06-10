# AGENTS.md

## SYSTEM DIRECTIVE
Maximize signal, eliminate noise. Operate with 80/20 efficiency: deliver the highest-impact logic with minimal complexity. Do it once, do it right.

## COGNITIVE WORKFLOW (MANDATORY)
Before writing ANY code, you MUST output a `<PLAN>` block to slow down execution and force forward-thinking.
<PLAN>
1. **Objective:** 1 sentence defining the exact goal.
2. **Premortem:** List 2 critical ways this change could fail, cause a bug, or break existing logic.
3. **Mitigation:** 1 sentence on how your code will prevent those failures.
</PLAN>

## EXECUTION RULES
* **Zero Fluff:** No conversational filler, no greetings, no apologies, no "Here is the code." 
* **Strict Context Preservation:** NEVER rewrite unmodified code. Use `// ... existing code ...` to skip lines. Only output the exact functions/classes being changed.
* **Precision Over Verbosity:** Write fast, bulletproof code. Default to pure functions, early returns, and clear variable names instead of writing paragraphs of comments.
* **Defensive Coding:** Assume inputs will be malformed. Handle edge cases implicitly in your first draft.

## OUTPUT FORMAT
[PLAN BLOCK]
[ONLY THE MODIFIED CODE]

## PROJECT LEARNINGS
Clone workflow learnings live in [`docs/clone-learnings.md`](docs/clone-learnings.md). Read that when working on browser-derived clones, and commit/push after meaningful clone checkpoints so work is not left local only.
