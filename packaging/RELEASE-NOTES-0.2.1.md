# Noteration 0.2.1

Noteration turns your study PDFs into notes, MCQs, flashcards, and an SM‑2
review schedule, all running locally on your machine. 0.2.1 brings a complete
offline generation path and an overnight batch mode, so you can hand the app a
stack of PDFs at night and wake up to everything already made.

---

## Local AI, from detection to install

Noteration can now run generation entirely on your own machine with no cloud
key. A guided setup in Settings looks at your hardware, picks two models that
actually fit, and installs them for you. It reads your GPU, VRAM, and system
memory (falling back gracefully when a value cannot be read), estimates how fast
each candidate model would run, and chooses a fast model for interactive work
and a higher‑quality model for the heavy overnight jobs. The quality model is
held to a real floor of at least ten tokens per second, so it is powerful
without being so large that it crawls.

Installing Ollama asks for admin rights only for that one step and only at the
moment you click install; everything else, the hardware checks, the model
downloads, and the model runs, stays unprivileged. If you would rather do it by
hand, the exact terminal commands are shown for you to copy.

## Pick your own local models

The Local AI section lists the Ollama models already on your machine and lets
you assign roles from a dropdown instead of typing a name. You can set one model
as the fast model, another as the slower but stronger one, or pin a single
"always" model that serves every local request regardless of the roles. The
always pin starts empty, so the automatic choice stays in charge until you
decide otherwise.

## Overnight everything

Two features make unattended, overnight study prep real. You can drop many PDFs
into a subject at once with the new overnight batch toggle in the upload dialog:
each file is ingested, its structure confirmed, and its topics queued, with a
bad file skipped rather than sinking the whole batch. And when you have a Gemini
key, a single toggle routes overnight generation through Gemini instead of the
local model, so the slow batch runs on the cloud while your interactive work
stays local.

## Study and focus

The study view now marks a topic with a checkmark once it is complete and adds a
small floating to‑do list you can keep beside your work. The Pomodoro
soundscape gained a gentler rain and four new synthesized noise presets for
focus.

## Linux desktop fixes

Audio playback, the duplicator white‑screen, and opening external links all work
correctly in the Linux desktop shell now.

---

## Install

The app is **unsigned**, so the first launch shows the usual OS warning. See
[`USER-GUIDE.md`](USER-GUIDE.md) for the click‑through on each platform.

| Platform | File | Notes |
|----------|------|-------|
| **Windows** | `Noteration-Setup-0.2.1.exe` | Per‑user installer, no admin needed |
| **macOS** | `Noteration-macOS.dmg` | Apple Silicon; drag to Applications |
| **Arch Linux** | `noteration-0.2.1-1-x86_64.pkg.tar.zst` | `sudo pacman -U` it |

Your notes, database, and cache live in a per‑user folder outside the install, so
upgrading over 0.2.0 keeps everything and applies any new migrations on first
launch.
