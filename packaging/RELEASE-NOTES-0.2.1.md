# Noteration 0.2.1

## Added

- **Local AI generation, fully offline.** A guided setup in Settings detects
  your GPU, VRAM, and system memory, estimates how fast each model would run,
  and installs two models that fit: a fast one for interactive work and a
  stronger one for overnight jobs. The quality model is held to a floor of at
  least ten tokens per second so it stays powerful without crawling.
- **Scoped Ollama install.** Admin rights are requested only for the Ollama
  install step and only when you click install; hardware checks, downloads, and
  model runs all stay unprivileged. The exact terminal commands are shown if you
  prefer to run them yourself.
- **Installed-model role pickers.** The Local AI section lists the Ollama models
  already on your machine and lets you assign the fast and quality roles from a
  dropdown, or pin one "always" model that serves every local request.
- **Overnight batch upload.** A new overnight toggle in the upload dialog lets
  you drop many PDFs into a subject at once; each is ingested, structured, and
  queued, with a bad file skipped rather than sinking the batch.
- **Overnight Gemini routing.** When a Gemini key is set, a toggle routes the
  heavy overnight lane through Gemini while your interactive work stays local.
- **Study checkmark and floating to-do list** in the study view.
- **New Pomodoro soundscapes:** a gentler rain plus four synthesized noise
  presets.

## Fixed

- Linux desktop shell: audio playback, the duplicator white screen, and opening
  external links all work correctly now.

---

## Install

The app is **unsigned**, so the first launch shows the usual OS warning.

| Platform | File | Notes |
|----------|------|-------|
| **Windows** | `Noteration-Setup-0.2.1.exe` | Per‑user installer, no admin needed |
| **macOS** | `Noteration-macOS.dmg` | Apple Silicon; drag to Applications |
| **Arch Linux** | `noteration-0.2.1-1-x86_64.pkg.tar.zst` | `sudo pacman -U` it |

Your notes, database, and cache live in a per‑user folder outside the install, so
upgrading over 0.2.0 keeps everything and applies any new migrations on first
launch.
