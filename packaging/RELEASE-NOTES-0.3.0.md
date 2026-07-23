# Noteration 0.3.0

![The library, organised into folders](https://raw.githubusercontent.com/Smaldy/Noteration/ceb9a07eb2b0c6d0390e5dc5b44d88ba94f04294/docs/screenshots/library-folders.png)

*The flat grid is gone. Folders can be tagged to a subject and fill themselves,
sit empty until you add something, or hold loose files by hand.*

![Inside a folder: colour groups](https://raw.githubusercontent.com/Smaldy/Noteration/ceb9a07eb2b0c6d0390e5dc5b44d88ba94f04294/docs/screenshots/folder-groups.png)

*Inside a folder, gather notes into named colour groups, with generated notes,
PDFs, and images side by side.*

![Recolour a folder and set the Main folder](https://raw.githubusercontent.com/Smaldy/Noteration/ceb9a07eb2b0c6d0390e5dc5b44d88ba94f04294/docs/screenshots/folder-settings.png)

*Pick a colour (or a custom one), tag a subject, and mark one folder Main so
generated notes always land in a single place.*

![The docked AI study sidebar](https://raw.githubusercontent.com/Smaldy/Noteration/ceb9a07eb2b0c6d0390e5dc5b44d88ba94f04294/docs/screenshots/ai-sidebar.png)

*The AI study sidebar answers from your own notes, grounded on a pinned topic,
and can run entirely offline.*

## Added

- **Folders replace the flat library.** The old grid grew unusable past a
  few dozen notes, so the library is now organised into folders. A folder can
  be tagged to a subject and then automatically shows every note in that
  subject, and you can also drop loose PDFs, images, or generated notes into
  any folder by hand. Each folder has its own colour and gets a distinct look
  when it is empty versus full.
- **Colour groups and a Main folder.** Inside a folder you can gather notes
  into named, coloured sub-groups, up to two levels deep. When several folders
  share the same subject tag, one of them can be marked the Main folder so
  newly generated notes always land in a single place instead of duplicating
  across all of them.
- **Generate, copy, and add in place.** An add button inside every folder
  covers the three common cases: generate fresh notes from a PDF, copy an
  existing note into another folder as a reference rather than a duplicate, or
  attach a plain file.
- **Folder and per-note bookmarks.** Bookmarks now star folders on the
  library, and inside a folder you can star individual notes for a quick
  shortlist that is scoped to that folder.
- **Docked AI study sidebar.** A grounded chat assistant sits alongside your
  study surfaces, answers from your own notes for the pinned topic, takes
  attachments, and stays within the bounds of the material rather than
  wandering off.
- **Per-PDF exam choices.** When preparing an exam deck you can now pick which
  question types to generate and the writing style, per PDF.

## Changed

- **A softer, pastel look** across the app, with a fixed left sidebar in place
  of the old top navigation.
- **Plainer wording** in generated notes, quizzes, and flashcards, so the
  output reads like a study partner instead of a textbook.

## Removed

- **Subject-level bookmarks**, which had no surface left to act on once
  bookmarking moved to folders. Your data is untouched; only the unused star
  is gone.

---

## Install

The app is **unsigned**, so the first launch shows the usual OS warning.

| Platform | File | Notes |
|----------|------|-------|
| **Windows** | `Noteration-Setup-0.3.0.exe` | Per-user installer, no admin needed |
| **macOS** | `Noteration-macOS.dmg` | Apple Silicon; drag to Applications |
| **Arch Linux** | `noteration-0.3.0-1-x86_64.pkg.tar.zst` | `sudo pacman -U` it |

Your notes, database, and cache live in a per-user folder outside the install,
so upgrading over 0.2.x keeps everything and applies the new folder migrations
on first launch.
