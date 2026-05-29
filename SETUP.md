# Setup — running the Noteration build with Ruflo

## File layout
Put these at your project root:
```
noteration/
├── CLAUDE.md          ← auto-loaded by Claude Code every session (lean rules)
├── RUFLO-BUILD.md     ← standing build contract (CLAUDE.md points here)
└── docs/              ← full spec + build-log.md (created on first run)
```

## One-time setup
```bash
# Claude Code (official tool — uses your Pro subscription)
npm install -g @anthropic-ai/claude-code

# Ruflo
npm install -g ruflo            # or: npx ruflo@latest ...

# In the project folder:
cd noteration/
```

> **Important on init:** `ruflo init` / `claude-flow init` generates its own
> `CLAUDE.md`. If you run it, it may overwrite yours. Either run init FIRST and
> then drop in your `CLAUDE.md`, or merge your rules into the generated one. Your
> build rules live in `RUFLO-BUILD.md` precisely so init can't clobber them.

## Don't paste the prompt — point at it
Don't paste `RUFLO-BUILD.md` into the chat each session (that re-loads ~700 words
every time). `CLAUDE.md` is auto-loaded and already points the swarm to
`RUFLO-BUILD.md` and `docs/`. Your kickoff is one short line.

## Kickoff (first session)
Initialize a tight, queen-led swarm and orchestrate against the docs. Exact flags
vary by Ruflo version — check `npx ruflo@latest --help` / the wiki first — but the
shape is:
```bash
# small, controlled swarm (not a giant fan-out)
npx ruflo@latest hive init --topology hierarchical --agents 3

# kick off, telling it to follow your contract
npx ruflo@latest orchestrate \
  "Build Noteration following RUFLO-BUILD.md and ./docs. Start with the \
start-of-session steps, then Phase 1 as the first wave." \
  --topology hierarchical --parallel
```

## Every later session
Just re-run `orchestrate` (or resume the hive). Because of `CLAUDE.md` + the
start-of-session ritual, the swarm will read `docs/build-log.md`, green-check, print
a RESUME SUMMARY, and continue — no re-pasting context.

## Watching usage / staying safe
- Check your window with `/status` and `/usage` inside Claude Code.
- Keep the agent count modest (3–5) so a wave finishes and checkpoints inside one
  5-hour window; raise it only if the window feels comfortable.
- With no `ANTHROPIC_API_KEY` set and credits disabled, work routes through your
  Pro subscription via Claude Code — no pay-as-you-go risk. If you ever see API
  billing, run `unset ANTHROPIC_API_KEY` and check `/status`.

## Version caveat
Ruflo is fast-moving alpha; command names (`hive`, `orchestrate`, `swarm`, `sparc`)
and flags shift between releases. Always verify against `npx ruflo@latest --help`
or the wiki before a session rather than trusting these exact strings.
