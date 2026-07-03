# Noteration 0.2.0

Noteration turns your study PDFs into notes, MCQs, flashcards, and an SM‑2
review schedule, all running locally on your machine. 0.2.0 is a major overhaul:
the whole interface was rebuilt on one design system, note generation now adapts
to what you study, and the desktop installers are properly built and verified on
every platform.

---

## A cohesive design system

The app now shares one visual language instead of per‑page styling. Every page is
built from the same shell (a common header, back link, section labels, and empty
states), status colors come from shared tokens, and there is one consistent
policy for corner radii, focus rings, and motion. Pick an accent color in
Settings and the entire palette is derived from it live, so the whole UI carries
one cohesive, readable color.

Every dropdown in the app now opens the same themed popover that follows your
accent color, with a check mark on the current choice, replacing the plain
grey menu the browser used to draw.

## Note generation that fits your subject

You can tune the AI tutor to your field of study, so engineering notes lean on
formulas, law notes focus on cases and statutes, and literature notes follow
themes and context. A separate writing‑style control sets how the notes are
worded, from plain and example‑led to concise or academic.

## Library and study

The library is cleaner and roomier: the subject filter now scopes the whole card
grid, you can create a subject inline, and deleting a document removes just that
PDF while leaving the rest of the subject intact. Reading is more comfortable
too, with a wider notes column in both the normal and full‑focus views and a
calmer full‑screen reading size.

## Settings you can shape

The Settings page is now yours to arrange. Drag sections into the order you want
and hide the ones you are done with (once your keys are set, you rarely need to
see them again); your layout is remembered. Typography is split into two choices,
one font for titles and one for body text, with a set of popular, highly readable
faces to pick from.

## Packaging and installers

The Windows installer now builds and passes its checks for the first time. Each
platform's bundle runs a headless self‑test on every build that confirms the
whole app is inside: the native libraries, the bundled ffmpeg, the AI provider
SDKs, the migrations, and the complete frontend with its fonts. The experimental,
never‑working portable Linux build was removed in favor of the proper Arch
package.

---

## Install

The app is **unsigned**, so the first launch shows the usual OS warning. See
[`USER-GUIDE.md`](USER-GUIDE.md) for the click‑through on each platform.

| Platform | File | Notes |
|----------|------|-------|
| **Windows** | `Noteration-Setup-0.2.0.exe` | Per‑user installer, no admin needed |
| **macOS** | `Noteration-macOS.dmg` | Apple Silicon; drag to Applications |
| **Arch Linux** | `noteration-0.2.0-1-x86_64.pkg.tar.zst` | `sudo pacman -U` it |

Your notes, database, and cache live in a per‑user folder outside the install, so
upgrading over 0.1.x keeps everything and applies any new migrations on first
launch.
