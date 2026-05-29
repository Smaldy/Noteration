# UX Flows

> Recovered from pasted chat history. Updated: local web app (no desktop shell);
> Study View = Option A (tabs within topic); Pomodoro = Option B (top bar strip);
> plus queue/cost states surfaced for the never-zero-result, cost-minimizing
> design (see `cost-strategy.md`).

## Screen map

```
First Launch
    └── Onboarding (API key setup)
            └── Home
Home
    ├── Upload PDF → Structure Review → [processing begins] → Study View
    └── Open existing document → Study View
Study View  (core of the app)
    ├── Notes tab
    ├── Quiz tab
    └── Flashcards tab
Calendar
Settings
```

## Screen by screen

### 1. First Launch / Onboarding
One-time screen shown when the app is first opened in the browser. Asks for the
API key(s) — Gemini free is the default path; the paid Claude key is optional and
the app works free-only without it. Briefly explains the free-first, process-what-
fits model. Saves and goes to Home. Never shown again unless a key is missing.

### 2. Home / Library
List of uploaded documents with title, upload date, exam date, and a progress
indicator (X of Y topics ready). Each document shows its **queue state**: "X ready
to study now · Y queued · resuming ~HH:MM" when a provider window is cooling down.
One large upload button. Click any document → Study View.

A persistent **status strip** (or the queue screen below) shows live spend
("spent $0.00 · saved vs. all-paid ~$X") and the active provider, keeping the
free-first mission visible.

### 3. Upload + Structure Review
Two-step flow triggered by upload:

- **Step 1:** file picker, markitdown runs, short loading state ("Reading your
  PDF...").
- **Step 2:** detected structure shown as an editable tree. Student renames,
  merges, splits topics. Assigns priority via a pill selector (exam-critical /
  medium / skip) inline per topic. Sets exam date here.
- **Pre-flight estimate** before confirming: "~N topics · ~H hours on free tier ·
  ~$0 unless paid fallback is used." Sets expectations for a large PDF up front.
- Confirm → topics enqueued (`skip` excluded), queue starts within free-tier
  budget, app opens Study View immediately (no waiting).

### 4. Study View — **Option A: tabs within topic** (locked)

```
┌─────────────────┬────────────────────────────────┐
│ SIDEBAR         │  [Notes] [Quiz] [Flashcards]   │
│                 │──────────────────────────────  │
│ ▶ Chapter 1     │  Topic content here            │
│   ✓ Topic 1     │                                │
│   ⟳ Topic 2     │                                │
│   … Topic 3     │  [PDF source page →]           │
│ ▶ Chapter 2     │                                │
└─────────────────┴────────────────────────────────┘
```

Notes, Quiz, and Flashcards are tabs inside the topic view — you're always
"inside" a topic, so switching between notes and quiz for the same topic needs no
re-navigation. Sidebar icons show per-topic status (✓ ready, ⟳ processing,
… queued, ! error→retry). Because a topic commits in sub-stages, a topic can read
"notes ready · questions pending" rather than a misleading single "ready."

### 5. Notes Tab

- AI note rendered as editable markdown (TipTap).
- `[reconstructed]` formulas (from vision transcription) highlighted; click to
  confirm → becomes `[verified]`.
- First navigation into a document: trust nudge banner at top ("Check
  reconstructed formulas before studying") — dismisses **per-document** on click
  (not globally), since formula quality varies by source PDF.
- Lock toggle + revert button appear on hover over any section.
- Manual notes can be added below the AI note as separate blocks.
- PDF source page displayed in a collapsible right panel.

### 6. Quiz Tab

- MCQ cards one at a time, full focus.
- Select answer → reveal correct answer with brief explanation.
- Keyboard navigable (1/2/3/4 to select, Enter to confirm).
- Progress bar at top (X of Y questions).
- Results summary at the end (score, which ones to review).

### 7. Flashcards Tab

- Single card centered, click or spacebar to flip (Framer Motion).
- Self-grade buttons after flip: Correct / Incorrect / Skip — these feed the SM-2
  scheduler.
- Progress indicator.
- Shuffle toggle.

### 8. Calendar

- FullCalendar month/week grid.
- Each day shows scheduled topics as blocks (populated by the SM-2 scheduler).
- Click a session block → Pomodoro timer starts, navigates into Study View for
  that topic.
- Revision buffer days visually distinct (different color).
- Drag-drop to reschedule.

**Pomodoro placement — Option B: top bar strip** (locked). A compact timer is
always visible in the header during a session — always in peripheral vision, less
intrusive than a floating widget.

### 9. Queue / Processing
A dedicated view for the never-zero-result model:

- Counts: ready to study now, processing, queued, errored.
- Resume countdown when a provider window is cooling ("resuming ~HH:MM").
- Active provider and the waterfall order; which provider generated each topic.
- Live spend vs. estimated all-paid cost.
- Per-topic retry for `error` rows; reorder/repriority while queued.
- An **overnight mode** toggle: "process everything on free tiers, however long it
  takes; notify me when exam-critical topics are done."

### 10. Settings
Single scrollable page:

- API keys: Gemini (free, default) and Claude (paid, optional) — masked inputs,
  test-connection buttons.
- **Provider waterfall:** reorder providers, toggle Ollama (local), and a hard
  **"never spend" switch** that disables the paid tier entirely (free-only).
- Pomodoro: work duration, break duration.
- Appearance: light/dark toggle, accent color picker, font family, font size.

## Resolved layout decisions

1. **Study View layout** → Option A (tabs within topic).
2. **Pomodoro timer placement** → Option B (top bar strip).
