# Invasion Update — 0.1.2v

Noteration turns your engineering PDFs into notes, MCQs, flashcards and an SM‑2
review schedule — all running locally on your machine. This update is all about
the thing hiding inside the app: a retro arcade minigame called **NOTINVASION**,
plus a batch of fixes (including proper math rendering across quizzes and cards).

---

## 🎮 NOTINVASION — the study arcade

A neon CRT shooter built *on top of* the real app. The twist: **the game is your
study tracker wearing an arcade cabinet.**

### How it works
- **You are the cursor.** Your mouse reticle is the player. **Click to fire** — a
  zap plus a burst of bullets (more bullets as you upgrade *Fire Rate*).
- **Survive waves.** Enemies pour in wave after wave. Clear a wave to advance; the
  deeper you go, the harder it gets — difficulty ramps every **10 waves**.
- **The app *is* the arena.** Each real page is a sector with its own themed
  enemies — the Calendar spawns **Clocks**, the Queue spawns **Hourglasses** — and
  you move between sectors using the app's *real* navigation buttons.
- **Bombs.** Live bombs make the real Library button glow. **Hold‑click to defuse**
  before they blow. Miss one and you take damage — and a streak of missed defuses
  hits *harder* each time (defusing any bomb resets the streak).
- **Hearts.** Get hit and you lose hearts. Bosses hit for **double**. Enemies have
  a **5% chance to drop a health orb**.

### 💰 Why you have to actually study
Coins are **only** earned by studying — there is no grind‑in‑game shortcut:
- **+1 coin** per flashcard reviewed
- **+1 coin** per MCQ answered
- **+3 bonus coins** for clearing the **daily quest** (15 MCQs in a day)

Coins are what you spend to **start a run** (a fresh run costs a few coins;
continuing a run costs more). So the loop is deliberate: **study → earn coins →
play.** Inside a run you earn **score points**, and *those* are what you spend in
the shop on upgrades. An anti‑binge cooldown caps how many runs you can start per
hour, so the game rewards steady studying rather than one marathon session.

---

## ✨ New in this update

### Smarter, fairer enemies
- **Exam‑prep beamers** no longer snipe you instantly — they now **aim → lock →
  fire**, with a visible telegraph, so the laser is dodgeable.
- **Hourglasses** do a real **flip animation**, and after flipping they **dash** at
  you (the little shards dash even faster) with a clear glowing‑lance tell.
- **The Clock boss is now an illusionist:** it teleports (sometimes right next to
  you), conjures **fake invulnerable clones** — each with a decoy health bar — and
  the *only* way to spot the real one is that **it's the one shooting at you**. It
  also hurls its **hour / minute / second hands** as spinning projectiles that
  regrow on its body.

### Performance & pacing
- A hard **cap on simultaneous enemies** to keep things smooth.
- Early waves spawn **less frequently** but with a **bigger total count**, and
  damage / spawn‑rate / bomb cadence escalate noticeably **every 10 waves**.
- **Bombs** now arrive on a randomized cadence instead of constantly.

### New abilities & upgrades
- **Defuser Pusher** — defusing a bomb releases a non‑damaging shockwave that
  shoves enemies back (on a cooldown you can shorten with upgrades).
- **Recall Beacon** — **hold right‑click** to warp back to the Library
  (hold time drops from 5s to 0.5s at max level).
- New shop upgrades: **Hollow Points** (bullet damage), **Railgun** (bullet
  speed + range), plus a Defuser Pusher cooldown track.
- The whole shop was **re‑tiered into 5 power tiers**, each unlocked by reaching a
  wave milestone (10 / 20 / 30 / 40).

### Prestige & special bullets (Tier 6)
- Reach wave 40 to **Prestige**: surrender all your upgrades in exchange for
  **+20% starting damage on every attack type** — and access to **Tier 6**.
- **Special bullets** (pick one, togglable):
  - ⚡ **Electric** — hits chain shared damage to nearby enemies.
  - 💗 **Love** — charm the enemy you hit so it **fights for you** (tougher enemies
    are harder to charm; bosses are immune). Charmed allies get hunted by the swarm.

### Reworked HUD
- A proper backing panel with glow so hearts, score and ability gauges stay
  **legible over the busy app behind them**.
- The HUD **adopts your selected app accent color** while keeping the arcade look.
- It **fades to transparent** when your cursor is over it — or when an enemy is
  behind it — so it never hides your reticle or a threat.

---

## 🐛 Bug fixes

- **Math now renders properly.** LaTeX / math expressions in **MCQ questions &
  answers** and **flashcards** are formatted correctly instead of showing raw
  delimiters — both inline and block math.
- Fixed an **infinite‑prestige** exploit; prestige now correctly **resets the wave
  goal** so you re‑climb to unlock tiers again.
- **Boss health increased 5×** (bosses were going down far too easily).
- **Missed‑defuse damage now escalates** with a streak (1 → 4 hearts); any
  successful defuse resets it.
- Retuned **boss dash** (much faster) and **hourglass dash** (farther, with a
  cleaner telegraph that replaced the old ugly one).
- Removed the leftover **Blockout (B)** button; developer‑only buttons are now
  **hidden** in normal builds.

---

## 💾 Downloads & install

| Platform | File | Notes |
|----------|------|-------|
| **Windows** | `Noteration-Setup-0.1.2.exe` | Per‑user installer, no admin needed |
| **macOS** | `Noteration-0.1.2.dmg` | Drag to Applications |
| **Arch Linux** | `noteration-0.1.2-1-x86_64.pkg.tar.zst` | `sudo pacman -U` it |

The app is **unsigned**, so first launch shows the usual OS warning:
- **Windows:** SmartScreen → *More info* → *Run anyway*.
- **macOS:** right‑click → *Open* the first time.

> **Note:** the Linux/Arch builds are new this release and still experimental — if
> the native window fails to open, make sure the system WebKit2GTK runtime is
> installed (`webkit2gtk-4.1` on Arch).

---

*Everything runs locally — your PDFs and study data never leave your machine.*
