# floss-icon-collections

Collection of some existed tango-flavoured icon packs taken from some FLOSS projects (GIMP, Inkscape, LibreOffice).

On the **upstreams** of these projects, the directory structure of these icons were **not** following to [XDG Icon Theme Specification](https://specifications.freedesktop.org/icon-theme/latest/). **This project is mean to rearrange them into the standard XDG-compatible icon theme directory structure**, which can be seamlessly directly used in the scenarios which follows XDG standard (For example, Qt's `QIcon::fromTheme()`).

I created this project mainly for [tango-remixer](https://github.com/kuanyui/tango-remixer/).

> [!TIP]
> To use these icons in a Qt (or GTK) project, see [Tango Remixer](https://kuanyui.github.io/tango-remixer/).
>
> You can also browse all icons in its [icon viewer](https://kuanyui.github.io/tango-remixer/viewer/).

# Source Project
## GIMP
- [Source repo](https://gitlab.gnome.org/GNOME/gimp-data/-/tree/main/icons?ref_type=heads)
- Icon Packs:
  - `GimpLegacy` (GPL v3+, licensed the same as GIMP application core)
  - `GimpDefault` (CC by-sa 3.0)

## Inkscape
- [Source repo](https://gitlab.com/inkscape/inkscape/-/tree/master/share/icons?ref_type=heads)
- Icon Packs:
  - `InkscapeTango` (GPL v2?)
- Donno why it was removed from repo of Inkscape since 2025/07/01
  https://gitlab.com/inkscape/inkscape/-/commit/7f2369a6a64088d070894110333ec8bdb6cc5372

## LibreOffice
- [Source repo](https://github.com/LibreOffice/core/tree/master/icon-themes/elementary_svg) (a mirror of https://git.libreoffice.org/core)
- Icon Packs:
  - `LibreOfficeElementary` (GPL v3. Some parts come from the Human icon theme under LGPL. See `LibreOfficeElementary/Copyrights`)
- Copied and renamed by a script, with the names that LibreOffice uses. See [upstream/LibreOffice/](upstream/LibreOffice/README.md).

# Disclosure of LLM Usage
## LibreOffice
LLM agent (Claude Code) is used in:

- Analyze the source code of LibreOffice, only for finding out the human-readable names of SVG icon files (which contains lots of magic number).
- Write Python script to rename the source SVG icon files into XDG-compatible icon theme directory structures.

## Art
- There is **not** any icon is drawn by LLM agent.
