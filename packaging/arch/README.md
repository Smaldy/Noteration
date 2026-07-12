# Arch Linux package

A native `pacman` package for Noteration, built from `PKGBUILD` with `makepkg`.
It wraps the project's PyInstaller one-folder freeze (the same build the Windows
and macOS installers ship) and lays it out the Arch way:

| Path | Contents |
|------|----------|
| `/opt/noteration/` | the frozen app bundle |
| `/usr/bin/noteration` | launcher symlink (run from a terminal or the menu) |
| `/usr/share/applications/noteration.desktop` | desktop / app-menu entry |
| `/usr/share/icons/hicolor/512x512/apps/noteration.png` | icon |

## Build & install (on Arch)

From this directory:

```bash
cd packaging/arch
makepkg -si        # builds, then installs with pacman (asks for sudo)
```

`makepkg` pulls the build tools it needs (`makedepends`): Node/npm for the
frontend bundle, Python + PyInstaller for the freeze, and the system
PyGObject/GTK so the GTK WebKit backend can be collected. The finished package
is `noteration-0.2.1-1-x86_64.pkg.tar.zst`.

To build without installing, then install separately:

```bash
makepkg -f
sudo pacman -U noteration-0.2.1-1-x86_64.pkg.tar.zst
```

Uninstall with `sudo pacman -R noteration`.

## Runtime dependencies

`pacman` installs these automatically with the package:

- `webkit2gtk-4.1` — the native window (pywebview's GTK/WebKit backend)
- `gtk3`, `glib2`

## Don't have an Arch machine?

The package is also built in CI in an `archlinux` container
(`.github/workflows/build-arch.yml`). It self-tests headlessly with `xvfb` and,
on a `v*` tag, attaches `noteration-*.pkg.tar.zst` to the GitHub release.
Download it from the **Actions** run (artifact `Noteration-Arch-pkg`) or the
release page, then `sudo pacman -U` it.
