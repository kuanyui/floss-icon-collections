# LibreOffice

`sync.py` copies the icons of a LibreOffice icon theme into an icon pack of this repository, such as `../../LibreOfficeElementary/`,
with the names that LibreOffice uses. So anyone can make the icon pack again.

```
upstream/LibreOffice/
├── sync.py                      The script. `--help` shows the naming rules
└── Elementary/                  One folder per theme. The icon pack is LibreOffice + the folder name
    ├── source_revision.txt      The upstream repository, branch, folder, and commit. Also the old branch for short names
    ├── filename_mapping.txt     The new path of each upstream file in LibreOfficeElementary/, or "-" if it is excluded
    ├── untouched_download/      Not in git. The upstream files as downloaded. The icons are in current/icon-themes/elementary_svg/
    └── excluded_from_pack/      Not in git. A copy of each excluded upstream file, by reason
```

## Commands

Run them at the root of this repository.

| Command                                                      | What it does                                                                                       |
|--------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| `python3 upstream/LibreOffice/sync.py Elementary`            | Make `LibreOfficeElementary/` again from the commit in `source_revision.txt`                       |
| `python3 upstream/LibreOffice/sync.py Elementary --latest`   | Update to the latest upstream commit. New upstream files get a name and a line in `filename_mapping.txt` |
| `python3 upstream/LibreOffice/sync.py Elementary --dry-run`  | Only report what would change                                                                      |
| `python3 upstream/LibreOffice/sync.py Elementary --rebuild-mapping` | Name every upstream file again from scratch                                                 |

## Names

The names come from upstream. No name is chosen by hand:

- A toolbar icon takes its LibreOffice command, split into words: `cmd/lc_insertannotation.svg` (`.uno:InsertAnnotation` in `officecfg/registry/data/org/openoffice/Office/UI/*Commands.xcu`) -> `actions/24/insert-annotation.svg`
- Another image takes its file name: `chart2/res/typepie_16.svg` -> `actions/16/typepie.svg`
- An image named by a short code takes its constant in `<module>/inc/bitmaps.hlst`: `res/lx03246.svg` (`BMP_OO_DRAW_DOC_LC`) -> `actions/24/oo-draw-doc.svg`
- A short code not in `bitmaps.hlst` takes its constant in the old resource files (`*.src`) of `libreoffice-5-1`: `dbaccess/res/lc039.svg` (`prefix = "lc"` + `ID_INDEX_SAVE` = 39) -> `actions/24/index-save.svg`
- A toolbar icon for one language (or for right-to-left text) ends with its folder name: `cmd/de/lc_bold.svg` -> `actions/24/bold-de.svg`, `cmd/rltb/32/defaultbullet.svg` -> `actions/32/default-bullet-rltb.svg`

- The size folder is the size declared in the SVG file. An unusual size such as 18 px goes to `scalable`, and the name keeps its size: `sc/res/sidebar/CellBorder_Left_18x18.svg` -> `actions/scalable/cell-border-left-18x18.svg`
- Excluded (`-` in `filename_mapping.txt`): images that are not square, and short codes that no upstream file explains.
- A name in `filename_mapping.txt` never changes on update. A changed upstream icon replaces the old copy. A `-` is tried again on each run.
- To use a standard name such as `document-open`, rename the icon in `included_icons.txt` of Tango Remixer.

## Needs

Git, Python 3.10+, and access to GitHub. The first run takes about 1 minute to download the needed files into `untouched_download/`.
