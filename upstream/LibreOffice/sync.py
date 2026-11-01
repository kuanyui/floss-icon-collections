#!/usr/bin/env python3
"""Copy the icons of a LibreOffice icon theme into an icon pack of this repository, with readable names from upstream.

Each theme has a folder `upstream/LibreOffice/<THEME>/`, and its icon pack is `LibreOffice<THEME>/`:

| File or folder         | Content |
|------------------------|---------|
| `source_revision.txt`  | The upstream repository, branch, folder, and the commit that the icon pack was made from. Also the old branch and commit for the short file names (see below) |
| `filename_mapping.txt` | One line per upstream file: the upstream path, then the new path in the icon pack |
| `untouched_download/`  | The upstream files as downloaded: `current/` for the commit, `legacy/` for the old branch. Not in git |
| `excluded_from_pack/`  | A copy of each upstream file that is not in the icon pack, by reason: `excluded_from_pack/not-square/<upstream path>`. Not in git |

In `filename_mapping.txt`, a new path of `-` means that the upstream file is excluded from the icon pack.
The upstream icons are in `untouched_download/current/<path in source_revision.txt>/`.

| Command                                            | What it does                                                          |
|----------------------------------------------------|-----------------------------------------------------------------------|
| `python3 upstream/LibreOffice/sync.py Elementary`  | Copy the icons of the commit in `source_revision.txt`                 |
| `... Elementary --latest`                          | Copy the icons of the latest commit, and update `source_revision.txt` |
| `... Elementary --commit <SHA>`                    | Copy the icons of another commit, and update `source_revision.txt`    |
| `... Elementary --dry-run`                         | Only report what would change                                         |
| `... Elementary --rebuild-mapping`                 | Name every upstream file again, from scratch                          |
| `... Elementary --prune`                           | Also delete the files of the icon pack not in `filename_mapping.txt`  |

How each run works:
1. Download only the needed files of the upstream commit into `untouched_download/current/`:
   the icon folder, the command lists, and the image constant lists (see below).
   Also the resource files of the old branch into `untouched_download/legacy/`. They never change.
2. Give a new path to each upstream file that has no line in `filename_mapping.txt` yet, by the rules below,
   and add the line. A new path in `filename_mapping.txt` never changes, so an icon keeps its name.
   A `-` is tried again, so an excluded file gets a name once upstream gives one.
3. Copy every mapped upstream file to its new path in the icon pack. A changed upstream file replaces
   the old copy. The copies of the files deleted upstream are kept.
4. Copy the excluded files to `excluded_from_pack/`, to see what they look like.

The rules give each upstream file a new path, from the names that upstream already uses:

| Upstream file                                    | New name                                                                |
|--------------------------------------------------|-------------------------------------------------------------------------|
| `cmd/sc_<command>.svg`, `cmd/lc_<command>.svg`, `cmd/32/<command>.svg` | The command (`.uno:InsertAnnotation` in `officecfg/registry/data/org/openoffice/Office/UI/*Commands.xcu`) split into words: `insert-annotation` |
| Another image with a readable file name          | The file name split into words, without its size: `typepie_16.svg` -> `typepie` |
| Another image with a short code as file name     | Its constant in `<module>/inc/bitmaps.hlst`: `res/lx03246.svg` = `BMP_OO_DRAW_DOC_LC` -> `oo-draw-doc` |
| A short code not in `bitmaps.hlst`               | Its constant in the resource files (`*.src`) of the old branch: `dbaccess/res/lc039.svg` = `ID_INDEX_SAVE` -> `index-save` |
| `cmd/de/`, `cmd/rltb/` and the like              | The name of the icon it replaces, with the folder name: `cmd/de/lc_bold.svg` -> `bold-de` |
| An image not square                              | Excluded                                                                |
| A short code with no constant                    | Excluded: upstream gives no readable name                               |
| A file other than SVG (the license files)        | The same path                                                           |

- The size folder is the size declared in the SVG file, or `scalable` for an unusual size such as 15 px.
  A name in `scalable` keeps the size of the upstream name: `placeholder_chart_small.svg` -> `placeholder-chart-small`.
  All icons go into the `actions` context.
- When two images get the same name and size, an image outside `cmd/` gets the name of its upstream
  top folder as prefix: `sc/res/sf01.svg` -> `sc-styles-family-cell`.
- The short codes come from LibreOffice 5.1 and older. An `ImageList` of a `.src` file named its images
  with its `Prefix`, a `0` when the number is below 10000, and the number of each constant in its `IdList`
  (`rsc/source/rsc/rsc.cxx`). In `dbaccess`, `prefix = "lc"` and `#define ID_INDEX_SAVE 39` make `lc039`.
  From LibreOffice 5.2, these resource files were removed bit by bit, so the old branch is `libreoffice-5-1`.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent
'''`upstream/LibreOffice/`, with one folder per theme, such as `Elementary/`.'''
REPO_ROOT: Path = PROJECT_ROOT.parent.parent

SOURCE_FILE: str = 'source_revision.txt'
MAPPING_FILE: str = 'filename_mapping.txt'
DOWNLOAD: str = 'untouched_download'
EXCLUDED: str = 'excluded_from_pack'

FIELD_SEPARATOR: re.Pattern[str] = re.compile(r'\t+| {4,}')
'''Fields are separated by tabs, or by 4 or more spaces, like `included_icons.txt` of Tango Remixer.'''

SKIP: str = '-'
'''The new path of an upstream file that is excluded from the icon pack.'''

CONTEXT: str = 'actions'
USUAL_SIZES: frozenset[int] = frozenset({16, 22, 24, 32, 48, 64, 96, 128, 256})

COMMANDS_XCU_GLOB: str = 'officecfg/registry/data/org/openoffice/Office/UI/*Commands.xcu'
'''The files that define the commands (`.uno:CommandName`).'''

BITMAP_LIST_GLOBS: list[str] = ['*/inc/bitmaps.hlst', 'include/vcl/bitmaps.hlst']
'''The files that give a constant name to image files (`BMP_OO_DRAW_DOC_LC = u"res/lx03246.png"`).'''

COMMAND_ICON: re.Pattern[str] = re.compile(r'^cmd/(?:(?:sc|lc)_(?P<name>[^/]+)|32/(?P<name32>[^/]+))\.svg$')
'''`cmd/sc_<command>.svg` is 16 px, `cmd/lc_<command>.svg` is 24 px, `cmd/32/<command>.svg` is 32 px.'''

VARIANT_ICON: re.Pattern[str] = re.compile(r'^cmd/(?P<before>(?:32/)?)(?P<variant>[a-z]{2}|rltb)/(?P<after>.+)$')
'''The icons that replace a toolbar icon for one UI language (`cmd/de/lc_bold.svg`), or for right-to-left layouts (`cmd/rltb/`).'''

SHORT_CODE: re.Pattern[str] = re.compile(r'[a-z]{1,4}\d+')
'''A file name that is not readable, such as `lx03246`, `sc20234` or `fr010`.'''

FILE_SIZE_PREFIX: re.Pattern[str] = re.compile(r'^(?:\d+x\d+_|[ls]c_)', re.IGNORECASE)
FILE_SIZE_SUFFIX: re.Pattern[str] = re.compile(r'(?:_\d+x\d+|_\d+(?:_\d+)?|_(?:small|big|large|extralarge))$', re.IGNORECASE)
CONSTANT_PREFIX: re.Pattern[str] = re.compile(r'^(?:RID_SVXBMP_|RID_CUIBMP_|RID_BMP_|SV_RESID_BITMAP_|BMP_|RID_|IMG_)')
CONSTANT_SIZE: re.Pattern[str] = re.compile(r'^\d+X\d+_|(?:_(?:LC|SC|L|BIG|\d+(?:X\d+)?))+$')

LEGACY_PATTERNS: list[str] = ['*.src', '*.hrc']
'''The resource files of the old branch. The headers that they include are downloaded too.'''

LEGACY_CONSTANT_PREFIX: re.Pattern[str] = re.compile(r'^(?:RID_SVXBMP_|RID_CUIBMP_|RID_BMP_|SV_RESID_BITMAP_|BMP_|RID_|IMG_|IID_|SID_|TBI_|FN_|ID_)')
'''The kinds of constants in the old resource files: images (`IMG_`, `IID_`), commands (`SID_`, `FN_`), toolbar items (`TBI_`, `ID_`).'''

C_CODE: re.Pattern[str] = re.compile(r'"(?:\\.|[^"\\\n])*"|/\*.*?\*/|//[^\n]*', re.DOTALL)
C_INCLUDE: re.Pattern[str] = re.compile(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"\n]+)[>"]', re.MULTILINE)
C_DEFINE: re.Pattern[str] = re.compile(r'^[ \t]*#[ \t]*define[ \t]+(\w+)(?![\w(])[ \t]*(.*)$', re.MULTILINE)
C_CAST: re.Pattern[str] = re.compile(r'\(\s*(?:sal_u?Int\d+|sal_uLong|sal_Bool|USHORT|ULONG|unsigned|int|long|short)\s*\)')

MAPPING_HEADER: str = '''\
# How each file of the upstream folder in source_revision.txt is renamed in ../../../{pack}/.
# Made by ../sync.py. See its help for the naming rules.
#
# <upstream path>    <new path in {pack}/, or "-" when the file is excluded (a copy is in excluded_from_pack/)>
'''

NOT_SQUARE: str = 'not square'
NO_NAME: str = 'no readable name upstream'
SAME_PATH: str = 'same new path as'


@dataclass(frozen=True)
class Source:
    repository: str
    branch: str
    path: str
    commit: str
    legacy_branch: str | None
    '''The old branch whose resource files tell what the short file names stand for. It does not change any more.'''
    legacy_commit: str | None

    @staticmethod
    def read(file: Path) -> 'Source':
        values: dict[str, str] = dict(read_pairs(file))
        missing: list[str] = [key for key in ('repository', 'branch', 'path', 'commit') if key not in values]
        if ('legacy-branch' in values) != ('legacy-commit' in values):
            missing.append('legacy-commit' if 'legacy-branch' in values else 'legacy-branch')
        if missing:
            sys.exit(f'{file}: missing {", ".join(missing)}')
        return Source(values['repository'], values['branch'], values['path'].strip('/'), values['commit'],
                      values.get('legacy-branch'), values.get('legacy-commit'))

    def write_commit(self, file: Path, commit: str) -> None:
        text: str = file.read_text(encoding='utf-8')
        text = re.sub(rf'^(commit(?:\t+| {{4,}})){re.escape(self.commit)}$', rf'\g<1>{commit}', text, count=1, flags=re.MULTILINE)
        file.write_text(text, encoding='utf-8')


def read_pairs(file: Path) -> list[tuple[str, str]]:
    """Read the lines of 2 fields. A `#` at the start of a line, or after a space or a tab, starts a comment."""
    pairs: list[tuple[str, str]] = []
    for line_number, line in enumerate(file.read_text(encoding='utf-8').splitlines(), start=1):
        line = re.sub(r'(?:^|\s)#.*$', '', line).strip()
        if not line:
            continue
        fields: list[str] = FIELD_SEPARATOR.split(line)
        if len(fields) != 2:
            sys.exit(f'{file}:{line_number}: expected 2 fields separated by a tab or 4+ spaces: {line!r}')
        pairs.append((fields[0], fields[1]))
    return pairs


def read_mapping(file: Path) -> dict[str, str]:
    """Return {upstream path: new path or `-`}. Stop on a duplicated upstream path or new path."""
    mapping: dict[str, str] = {}
    owner_of_new_path: dict[str, str] = {}
    for old, new in read_pairs(file) if file.exists() else []:
        if old in mapping:
            sys.exit(f'{file}: the upstream path is listed twice: {old}')
        if new != SKIP:
            if new.startswith('/') or '..' in Path(new).parts:
                sys.exit(f'{file}: the new path must be inside the icon pack: {new}')
            if new in owner_of_new_path:
                sys.exit(f'{file}: {old} and {owner_of_new_path[new]} have the same new path: {new}')
            owner_of_new_path[new] = old
        mapping[old] = new
    return mapping


def write_mapping(file: Path, pack: str, mapping: dict[str, str]) -> None:
    width: int = max(len(old) for old in mapping) + 4
    lines: list[str] = [f'{old:<{width}}{mapping[old]}\n' for old in sorted(mapping)]
    file.write_text(MAPPING_HEADER.format(pack=pack) + '\n' + ''.join(lines), encoding='utf-8')


def split_words(name: str) -> str:
    """Split a name into lower-case words joined by `-`: `ExportDirectToPDF` -> `export-direct-to-pdf`.

    Only the upper-case letters start a new word, so a lower-case part stays as it is: `a11y`, `3dgeo`.
    """
    words: list[str] = []
    for part in re.split(r'[._\-\s]+', name):
        if part.islower() or part.isdigit():
            words.append(part)
        else:
            words += re.findall(r'\d+[A-Z]+(?![a-z])|[A-Z]\d+(?![a-z\d])|[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+(?:\d+(?![A-Z]))?|[A-Z]+|\d+', part)
    return '-'.join(word.lower() for word in words if word)


def svg_size(file: Path) -> str:
    """Return the size declared in the `<svg>` tag, such as `16x16`, or `?`."""
    head: str = file.read_text(encoding='utf-8', errors='replace')[:4000]
    tag: re.Match[str] | None = re.search(r'<svg\b[^>]*>', head, re.DOTALL)
    if not tag:
        return '?'
    width = re.search(r'\bwidth="([\d.]+)(?:px)?"', tag.group())
    height = re.search(r'\bheight="([\d.]+)(?:px)?"', tag.group())
    if width and height:
        return f'{float(width.group(1)):g}x{float(height.group(1)):g}'
    view_box = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', tag.group())
    if view_box:
        return f'{float(view_box.group(1)):g}x{float(view_box.group(2)):g}'
    return '?'


def git(cache: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(cache), *args], check=True, capture_output=True, text=True).stdout.strip()


def sparse_patterns(cache: Path) -> list[str]:
    """Return the patterns of the files that the cache checks out."""
    result = subprocess.run(['git', '-C', str(cache), 'sparse-checkout', 'list'], capture_output=True, text=True)
    return result.stdout.splitlines() if result.returncode == 0 else []


def set_sparse_patterns(cache: Path, patterns: list[str]) -> None:
    """Check out the files that match `patterns`. Skipped when nothing changes, because git rewrites its whole index."""
    if not set(patterns) <= set(sparse_patterns(cache)):
        git(cache, 'sparse-checkout', 'set', '--no-cone', *patterns)


def fetch(cache: Path, repository: str, ref: str, patterns: list[str]) -> str:
    """Download only the files of `ref` that match `patterns` into `cache`, and return the commit SHA."""
    if not (cache / '.git').exists():
        cache.mkdir(parents=True, exist_ok=True)
        git(cache, 'init', '--quiet')
        git(cache, 'remote', 'add', 'origin', repository)
        git(cache, 'config', 'remote.origin.promisor', 'true')
        git(cache, 'config', 'remote.origin.partialclonefilter', 'blob:none')
    git(cache, 'remote', 'set-url', 'origin', repository)
    set_sparse_patterns(cache, patterns)
    if re.fullmatch(r'[0-9a-f]{40}', ref) and subprocess.run(['git', '-C', str(cache), 'rev-parse', '--verify', '--quiet', 'HEAD'],
                                                             capture_output=True, text=True).stdout.strip() == ref:
        return ref  # This commit is already in the cache.
    print(f'Fetching {ref} of {repository} ...', file=sys.stderr)
    git(cache, 'fetch', '--quiet', '--depth', '1', '--filter=blob:none', 'origin', ref)
    commit: str = git(cache, 'rev-parse', 'FETCH_HEAD')
    git(cache, 'checkout', '--quiet', '--force', '--detach', commit)
    return commit


def strip_c_comments(text: str) -> str:
    """Join the lines that end with `\\`, and replace the comments with a space, like the C preprocessor."""
    text = re.sub(r'\\\r?\n', ' ', text)
    return C_CODE.sub(lambda code: code.group() if code.group().startswith('"') else ' ', text)


def braced(text: str, start: int) -> str:
    """Return the text inside the braces that open at `text[start]`."""
    depth: int = 0
    for index in range(start, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    return text[start + 1:]


class LegacyNames:
    """The constants that the short file names stand for, read from the resource files of an old LibreOffice.

    Up to LibreOffice 5.x, an `ImageList` of a `.src` file named its image files with its `Prefix`,
    a `0` when the number is below 10000, and the number of each constant in its `IdList`
    (see `rsc/source/rsc/rsc.cxx`). So `prefix = "lc"` with `ID_INDEX_SAVE` (39) is `lc039`.
    An `Image` or `Bitmap` of a `.src` file can also name its file directly: `Image IMG_X { ... File = "lc06303.bmp" }`.
    """

    def __init__(self, cache: Path, repository: str, commit: str, label: str) -> None:
        self.cache: Path = cache
        self.label: str = label
        fetch(cache, repository, commit, LEGACY_PATTERNS)
        self.paths: set[str] = set(git(cache, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines())
        self.by_name: defaultdict[str, list[str]] = defaultdict(list)
        for path in sorted(self.paths):
            self.by_name[path.rsplit('/', 1)[-1]].append(path)
        self.parsed: dict[str, tuple[dict[str, str], list[str]]] = {}
        self.texts: dict[str, str] = {}
        self.on_disk: set[str] = set(list_files(cache))
        self.check_out_includes()
        self.codes: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
        '''{short code: {(module, constant)}}, such as {'lc039': {('dbaccess', 'ID_INDEX_SAVE')}}'''
        for src in sorted(path for path in self.paths if path.endswith('.src')):
            self.read_resources(src)

    def resource_files(self) -> list[str]:
        return sorted(path for path in self.paths if path.endswith(('.src', '.hrc')))

    def check_out_includes(self) -> None:
        """Download the headers that the resource files include, until nothing is missing."""
        extra: set[str] = {pattern.removeprefix('/') for pattern in sparse_patterns(self.cache) if pattern not in LEGACY_PATTERNS}
        while True:
            needed: set[str] = set()
            for path in self.resource_files():
                needed.update(self.include_closure(path))
            missing: set[str] = {path for path in needed if path not in self.on_disk} - extra
            if not missing:
                return
            extra |= missing
            set_sparse_patterns(self.cache, [*LEGACY_PATTERNS, *sorted(f'/{path}' for path in extra)])
            self.on_disk = set(list_files(self.cache))
            self.parsed.clear()
            self.texts.clear()

    def resolve_include(self, name: str, including: str) -> str | None:
        """Find the file of `#include <name>` or `#include "name"`: next to `including`, else in its module, else anywhere."""
        beside: str = os.path.normpath(os.path.join(os.path.dirname(including), name))
        if beside in self.paths:
            return beside
        candidates: list[str] = [path for path in self.by_name.get(name.rsplit('/', 1)[-1], []) if path == name or path.endswith('/' + name)]
        module: str = including.split('/', 1)[0]
        return next((path for path in candidates if path.split('/', 1)[0] == module), None) \
            or next((path for path in candidates if path.startswith('include/')), None) \
            or (candidates[0] if candidates else None)

    def parse(self, path: str) -> tuple[dict[str, str], list[str]]:
        """Return ({macro: value}, [included files]) of a file. A file not downloaded yet has none."""
        if path not in self.parsed:
            text: str = self.text(path)
            defines: dict[str, str] = {}
            for define in C_DEFINE.finditer(text):
                defines.setdefault(define.group(1), define.group(2).strip())
            includes: list[str] = []
            for include in C_INCLUDE.finditer(text):
                resolved: str | None = self.resolve_include(include.group(1).strip(), path)
                if resolved and resolved not in includes:
                    includes.append(resolved)
            self.parsed[path] = (defines, includes)
        return self.parsed[path]

    def include_closure(self, path: str) -> list[str]:
        """Return `path` and every file that it includes, directly or not, in the order of the C preprocessor."""
        order: list[str] = []
        stack: list[str] = [path]
        while stack:
            current: str = stack.pop()
            if current in order:
                continue
            order.append(current)
            stack.extend(reversed(self.parse(current)[1]))
        return order

    def macros(self, path: str) -> dict[str, str]:
        """Return the macros that `path` can use. The first definition wins."""
        macros: dict[str, str] = {}
        for file in self.include_closure(path):
            for name, value in self.parse(file)[0].items():
                macros.setdefault(name, value)
        return macros

    @staticmethod
    def evaluate(name: str, macros: dict[str, str], depth: int = 0) -> int | None:
        """Return the number of a macro such as `#define ID_INDEX_SAVE 39`, or None."""
        if depth > 50 or name not in macros:
            return None

        def value(token: re.Match[str]) -> str:
            text: str = token.group()
            if text[0].isdigit():
                text = text.rstrip('uUlL')
                return str(int(text, 16) if text[:2] in ('0x', '0X') else int(text, 8) if len(text) > 1 and text[0] == '0' else int(text))
            number: int | None = LegacyNames.evaluate(text, macros, depth + 1)
            if number is None:
                raise LookupError(text)
            return str(number)

        try:
            expression: str = re.sub(r'\b(?:0[xX][0-9a-fA-F]+|\d+)[uUlL]*\b|\b[A-Za-z_]\w*\b', value, C_CAST.sub(' ', macros[name]))
        except LookupError:
            return None
        if not re.fullmatch(r'[\d\s+\-*/%()|&^~<>]*\d[\d\s+\-*/%()|&^~<>]*', expression):
            return None
        try:
            return int(eval(expression.replace('/', '//'), {'__builtins__': {}}, {}))
        except (SyntaxError, ArithmeticError, TypeError):
            return None

    def text(self, path: str) -> str:
        """Return the text of a file without comments. A file not downloaded yet is empty."""
        if path not in self.texts:
            self.texts[path] = strip_c_comments((self.cache / path).read_text(encoding='utf-8', errors='replace')) if path in self.on_disk else ''
        return self.texts[path]

    def read_resources(self, src: str) -> None:
        """Add the short codes of the `ImageList`s, `Image`s and `Bitmap`s of a `.src` file."""
        text: str = self.text(src)
        if 'ImageList' not in text and 'File' not in text:
            return
        module: str = src.split('/', 1)[0]
        macros: dict[str, str] = self.macros(src)
        for image_list in re.finditer(r'\bImageList\b\s*\w*\s*\{', text):
            body: str = braced(text, image_list.end() - 1)
            for _ in range(5):
                body = re.sub(r'\b[A-Z_][A-Z0-9_]*\b', lambda word: macros[word.group()] if 'IdList' in macros.get(word.group(), '') else word.group(), body)
            prefix = re.search(r'\bprefix\s*=\s*"([^"]*)"', body, re.IGNORECASE)
            id_list = re.search(r'\bIdList\s*=\s*\{([^}]*)\}', body)
            if not prefix or not id_list:
                continue
            for constant in (word.strip() for word in id_list.group(1).split(';')):
                number: int | None = self.evaluate(constant, macros) if constant else None
                if number is not None:
                    self.codes[f'{prefix.group(1)}{"0" if number < 10000 else ""}{number}'].add((module, constant))
        for resource in re.finditer(r'\b(?:Image|Bitmap)\s+([A-Za-z_]\w*)\s*\{', text):
            file_name = re.search(r'\bFile\s*=\s*"([^"]+)"', braced(text, resource.end() - 1))
            if file_name:
                self.codes[file_name.group(1).rsplit('/', 1)[-1].rsplit('.', 1)[0]].add((module, resource.group(1)))

    def constant(self, old: str, upstream_files: set[str]) -> tuple[str | None, str]:
        """Return (the old constant of an upstream file, or None; the reason).

        The old LibreOffice looked for the image of a module in `<module>/res/` first, then in `res/`
        (the `-lip` options in `solenv/gbuild/AllLangResTarget.mk`). So a file in a module folder,
        such as `dbaccess/res/lc039.svg`, takes a constant of that module. A file in `res/` takes
        a constant of a module that has no file of that name in its own `<module>/res/`.
        """
        folder, _, file_name = old.rpartition('/')
        code: str = file_name.removesuffix('.svg')
        found: set[tuple[str, str]] = self.codes.get(code, set())
        if folder == 'res':
            constants: list[str] = sorted({constant for owner, constant in found if f'{owner}/res/{file_name}' not in upstream_files})
        else:
            constants = sorted({constant for owner, constant in found if f'{owner}/res' == folder})
        if len(constants) == 1:
            return constants[0], f'{constants[0]} in {self.label}'
        if constants:
            return None, f'more than one constant in {self.label}: {", ".join(constants)}'
        return None, NO_NAME


def list_files(folder: Path) -> list[str]:
    """Return the files in `folder`, without `.git/`. `os.walk` needs no `stat` per file, which is slow on some disks."""
    files: list[str] = []
    for root, folders, names in os.walk(folder):
        folders[:] = [name for name in folders if name != '.git']
        relative: str = Path(root).relative_to(folder).as_posix()
        files += (name if relative == '.' else f'{relative}/{name}' for name in names)
    return sorted(files)


def git_blob_ids(cache: Path, folder: str) -> dict[str, str]:
    """Return {path in `folder`: git blob id} of the commit in the cache, without reading the files."""
    ids: dict[str, str] = {}
    for line in git(cache, 'ls-tree', '-r', 'HEAD', '--', f'{folder}/').splitlines():
        info, _, path = line.partition('\t')
        ids[path.removeprefix(f'{folder}/')] = info.split()[2]
    return ids


def file_blob_id(file: Path) -> str | None:
    """Return the git blob id of a file, or None when it does not exist."""
    try:
        data: bytes = file.read_bytes()
    except FileNotFoundError:
        return None
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


class Namer:
    """Name the upstream files by the rules in the help of this script."""

    def __init__(self, cache: Path, source: Source, legacy: LegacyNames | None) -> None:
        self.icons: Path = cache / source.path
        self.legacy: LegacyNames | None = legacy
        self.upstream_files: set[str] = set(list_files(self.icons))
        self.commands: dict[str, str] = {}
        '''{lower-case command: command}, such as {'insertannotation': 'InsertAnnotation'}'''
        for xcu in sorted(cache.glob(COMMANDS_XCU_GLOB)):
            for node in re.finditer(r'<node oor:name="\.uno:([^"]+)"', xcu.read_text(encoding='utf-8')):
                self.commands.setdefault(node.group(1).lower(), node.group(1))
        self.constants: defaultdict[str, list[str]] = defaultdict(list)
        '''{image path without extension: [constants]}, such as {'res/lx03246': ['BMP_OO_DRAW_DOC_LC']}'''
        for glob in BITMAP_LIST_GLOBS:
            for bitmap_list in sorted(cache.glob(glob)):
                for constant in re.finditer(r'(\w+)\s*=\s*u"([^"]+)\.png"', bitmap_list.read_text(encoding='utf-8')):
                    self.constants[constant.group(2)].append(constant.group(1))

    def name(self, old: str) -> tuple[str | None, str]:
        """Return (new path, or None when the file is excluded; the reason)."""
        if not old.endswith('.svg'):
            return old, 'not an SVG file'
        width, _, height = svg_size(self.icons / old).partition('x')
        if width != height or not width.replace('.', '', 1).isdigit():
            return None, f'{NOT_SQUARE}: {width}x{height}'
        size: str = width if width.isdigit() and int(width) in USUAL_SIZES else 'scalable'
        variant = VARIANT_ICON.match(old)
        if variant:
            readable, reason = self.readable_name(f'cmd/{variant["before"]}{variant["after"]}', size == 'scalable')
            if readable is None:
                return None, reason
            return f'{CONTEXT}/{size}/{readable}-{variant["variant"]}.svg', f'{reason}, for {variant["variant"]}'
        readable, reason = self.readable_name(old, size == 'scalable')
        if readable is None:
            return None, reason
        return f'{CONTEXT}/{size}/{readable}.svg', reason

    def readable_name(self, old: str, keep_size: bool) -> tuple[str | None, str]:
        """Return (the readable name of an upstream file, or None when upstream gives none; where it comes from).

        With `keep_size`, the size in a file name or a constant stays in the name, because the icons
        in `scalable/` have no size folder to tell `placeholder_chart_small` from `placeholder_chart_large`."""
        command = COMMAND_ICON.match(old)
        if command:
            name: str = command.group('name') or command.group('name32')
            readable: str = split_words(self.commands.get(name, name))
            reason: str = f'.uno:{self.commands[name]}' if name in self.commands else 'file name'
        else:
            stem: str = old.rsplit('/', 1)[-1].removesuffix('.svg')
            if not keep_size:
                stem = FILE_SIZE_SUFFIX.sub('', FILE_SIZE_PREFIX.sub('', stem))
            if not SHORT_CODE.fullmatch(stem.lower()):
                readable, reason = split_words(stem), 'file name'
            elif self.constants.get(old.removesuffix('.svg')):
                constant: str = self.constants[old.removesuffix('.svg')][0]
                constant_name: str = CONSTANT_PREFIX.sub('', constant)
                readable, reason = split_words(constant_name if keep_size else CONSTANT_SIZE.sub('', constant_name)), constant
            else:
                constant, reason = self.legacy.constant(old, self.upstream_files) if self.legacy else (None, NO_NAME)
                if constant is None:
                    return None, reason
                constant_name = LEGACY_CONSTANT_PREFIX.sub('', constant)
                readable = split_words(constant_name if keep_size else CONSTANT_SIZE.sub('', constant_name))
        return readable, reason

    @staticmethod
    def with_prefix(old: str, new: str) -> str | None:
        """The new path with the upstream top folder as prefix, for an image outside `cmd/`."""
        if old.startswith('cmd/'):
            return None
        folder, _, name = new.rpartition('/')
        return f'{folder}/{split_words(old.split("/", 1)[0])}-{name}'

    def name_all(self, olds: list[str], taken: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
        """Name `olds`, avoiding the new paths in `taken` ({new path: upstream path}). Return ({old: new}, {old: reason})."""
        named: dict[str, str] = {}
        reasons: dict[str, str] = {}
        for old in olds:
            new, reasons[old] = self.name(old)
            named[old] = new or SKIP
        owners: defaultdict[str, list[str]] = defaultdict(list)
        for old, new in named.items():
            if new != SKIP:
                owners[new].append(old)
        for new, olds_of_new in owners.items():
            if len(olds_of_new) == 1 and new not in taken:
                continue
            for old in olds_of_new:
                prefixed: str | None = self.with_prefix(old, new)
                if prefixed:
                    named[old] = prefixed
                    reasons[old] += ', with prefix: same name as another image'
        seen: dict[str, str] = dict(taken)
        for old in olds:
            new = named[old]
            if new != SKIP and new in seen:
                named[old] = SKIP
                reasons[old] = f'{SAME_PATH} {seen[new]}'
            elif new != SKIP:
                seen[new] = old
        return named, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('theme', help=f'the folder of the theme in upstream/{PROJECT_ROOT.name}/, such as Elementary.'
                                      f' Its icon pack is {PROJECT_ROOT.name}<THEME>')
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--latest', action='store_true', help='use the latest commit of the branch in source_revision.txt')
    target.add_argument('--commit', help='use this commit instead of the one in source_revision.txt')
    parser.add_argument('--rebuild-mapping', action='store_true', help='name every upstream file again, ignoring filename_mapping.txt')
    parser.add_argument('--dry-run', action='store_true', help='only report; change no file')
    parser.add_argument('--prune', action='store_true', help='delete the files of the icon pack that are not in filename_mapping.txt')
    parser.add_argument('--download-dir', type=Path, help=f'where to download the upstream files (default: {DOWNLOAD}/ in the folder of the theme)')
    args = parser.parse_args()

    theme_folder: Path = PROJECT_ROOT / args.theme
    if not (theme_folder / SOURCE_FILE).is_file():
        sys.exit(f'{theme_folder / SOURCE_FILE}: not found')
    pack_name: str = PROJECT_ROOT.name + args.theme
    source_file: Path = theme_folder / SOURCE_FILE
    mapping_file: Path = theme_folder / MAPPING_FILE
    pack: Path = REPO_ROOT / pack_name
    download: Path = args.download_dir or theme_folder / DOWNLOAD
    source: Source = Source.read(source_file)
    mapping: dict[str, str] = {} if args.rebuild_mapping else read_mapping(mapping_file)

    ref: str = source.branch if args.latest else (args.commit or source.commit)
    commit: str = fetch(download / 'current', source.repository, ref,
                        [f'/{source.path}/', f'/{COMMANDS_XCU_GLOB}', *(f'/{glob}' for glob in BITMAP_LIST_GLOBS)])
    legacy: LegacyNames | None = None
    if source.legacy_branch and source.legacy_commit:
        legacy = LegacyNames(download / 'legacy', source.repository,
                             source.legacy_commit, source.legacy_branch)
    namer = Namer(download / 'current', source, legacy)
    upstream_files: list[str] = sorted(namer.upstream_files)

    # An excluded file is named again on each run, so it gets a name once upstream gives one.
    new_files: list[str] = [old for old in upstream_files if old not in mapping]
    retried: list[str] = [old for old in upstream_files if mapping.get(old) == SKIP]
    taken: dict[str, str] = {new: old for old, new in mapping.items() if new != SKIP}
    named, reasons = namer.name_all(sorted(new_files + retried), taken)
    mapping.update(named)

    blob_ids: dict[str, str] = git_blob_ids(download / 'current', source.path)
    counts: dict[str, int] = {'added': 0, 'updated': 0, 'unchanged': 0, 'excluded': 0}
    for old in upstream_files:
        new: str = mapping[old]
        if new == SKIP:
            counts['excluded'] += 1
            continue
        src: Path = namer.icons / old
        dst: Path = pack / new
        copy_id: str | None = file_blob_id(dst)
        if copy_id is None:
            counts['added'] += 1
        elif copy_id != blob_ids[old]:
            counts['updated'] += 1
        else:
            counts['unchanged'] += 1
            continue
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

    print(f'{pack_name}: {source.repository} {source.path} @ {commit}' + ('' if commit == source.commit else f' (was {source.commit})'))
    print('  ' + ', '.join(f'{count} {name}' for name, count in counts.items()) + (' (dry run)' if args.dry_run else ''))

    named_now: list[str] = [old for old in retried if named[old] != SKIP]
    for title, olds in ((f'New upstream files, added to filename_mapping.txt ({len(new_files)}):', [] if args.rebuild_mapping else new_files),
                        (f'Excluded before, named now ({len(named_now)}):', named_now)):
        if olds:
            print(f'\n{title}')
            width: int = max(len(old) for old in olds) + 4
            for old in olds:
                print(f'  {old:<{width}}{named[old]:<56}# {reasons[old]}')

    excluded: dict[str, str] = {}
    '''{upstream path: folder in excluded_from_pack/}'''
    for old in upstream_files:
        if mapping[old] == SKIP:
            reason: str = reasons[old]
            excluded[old] = 'not-square' if reason.startswith(NOT_SQUARE) else 'same-name' if reason.startswith(SAME_PATH) else 'no-name'
    excluded_root: Path = theme_folder / EXCLUDED
    print(f'\nExcluded, copied to {excluded_root.relative_to(REPO_ROOT)}/: '
          + ', '.join(f'{folder} {list(excluded.values()).count(folder)}' for folder in sorted(set(excluded.values()))))
    for old, folder in excluded.items():
        if folder != 'not-square':
            print(f'  {folder}/{old:<56}# {reasons[old]}')
    if not args.dry_run:
        shutil.rmtree(excluded_root, ignore_errors=True)
        for old, folder in excluded.items():
            (excluded_root / folder / old).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(namer.icons / old, excluded_root / folder / old)

    upstream_set: set[str] = set(upstream_files)
    gone: list[str] = [old for old, new in mapping.items() if new != SKIP and old not in upstream_set]
    if gone:
        print(f'\nDeleted upstream, so not updated any more ({len(gone)}). Their copies are kept:')
        for old in gone:
            print(f'  {old}    {mapping[old]}')

    kept: set[str] = {new for new in mapping.values() if new != SKIP}
    orphans: list[str] = [path for path in list_files(pack) if path not in kept] if pack.exists() else []
    if orphans:
        deleting: bool = args.prune and not args.dry_run
        print(f'\nNot in filename_mapping.txt ({len(orphans)}):' + (' deleted' if deleting else ' (use --prune to delete them)'))
        for path in orphans:
            print(f'  {path}')
            if deleting:
                (pack / path).unlink()
        if deleting:
            for folder in sorted((path for path in pack.rglob('*') if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
                if not any(folder.iterdir()):
                    folder.rmdir()

    if not args.dry_run:
        write_mapping(mapping_file, pack_name, mapping)
        if commit != source.commit:
            source.write_commit(source_file, commit)
    return 0


if __name__ == '__main__':
    sys.exit(main())
