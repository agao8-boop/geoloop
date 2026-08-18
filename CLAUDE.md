# Handoff protocol (Claude Code, implementer role)

You are being invoked headless by Codex, which is orchestrating on behalf of Almanzo.

1. Read `.handoff/TASK.md` first. It is your only instruction source for this run. Ignore any
   assumption you carry about what "the task" is until you have read it.
2. `MODE: plan` means write your plan into `.handoff/RESULT.md` and stop. Do not modify any code.
3. `MODE: implement` means build it, then run every command in the TASK.md `VERIFY WITH` block
   yourself and paste the real output.
4. Always finish by writing `.handoff/RESULT.md` containing:
   - WHAT CHANGED: file:line for each edit
   - COMMANDS RUN: the exact commands
   - OUTPUT: actual pasted output, not a summary of it
   - NOT DONE: anything in MUST DO you did not complete, and why
   - ASSUMPTIONS: any ambiguity you resolved yourself
5. Never write a `VERDICT` line. Pass or fail is Codex's call, not yours.
6. You cannot ask questions in this mode. If TASK.md is ambiguous, implement the most defensible
   reading and record it under ASSUMPTIONS. Do not stall.
7. Stay inside the MUST NOT fence in TASK.md. Scope creep is a failure even if the extra work is good.
