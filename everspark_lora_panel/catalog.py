"""Read the LoRA Vault formats written by the existing import scripts."""

import json
import re
import shlex
from collections import Counter, defaultdict
from functools import cached_property
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from .thumbnail_names import legacy_stem, normalize_vault_path, thumb_cache_name_from_md_path, vault_thumb_name

IMAGE_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
}
FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", re.S)
FIELD = re.compile(r"^([a-zA-Z_][\w-]*):[ \t]*(.*)$")
EMBED = re.compile(r"!\[\[([^\]]+)\]\]|!\[[^\]]*\]\((<[^>]+>|[^)]+)\)")
FIELDS = (
    "lora_name", "lora_version", "category", "model_support", "effect",
    "notes", "trigger_words", "download_url", "pod_loaded", "tested",
)


def scalar(value):
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except ValueError:
            return value[1:-1].replace(r'\"', '"')
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except ValueError:
            lexer = shlex.shlex(value[1:-1], posix=True)
            lexer.whitespace = ","
            lexer.whitespace_split = True
            lexer.commenters = ""
            try:
                return [part.strip() for part in lexer if part.strip()]
            except ValueError:
                return value
    return re.split(r"\s+#", value, maxsplit=1)[0]


def metadata(text):
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    values = {}
    key = None
    for line in match[1].splitlines():
        field = FIELD.match(line)
        if field:
            key, value = field.groups()
            values[key] = scalar(value)
        elif key and line.startswith((" ", "\t")):
            part = line.strip()
            if part.startswith("- ") and isinstance(values[key], (str, list)):
                if not values[key]:
                    values[key] = []
                if isinstance(values[key], list):
                    values[key].append(scalar(part[2:]))
                    continue
            if isinstance(values[key], str):
                if values[key] in {">", ">-", ">+", "|", "|-", "|+"}:
                    values[key] = part
                elif part:
                    values[key] += "\n" + part
    return values, text[match.end():]


def inside(path, root):
    result = path.resolve()
    return result if result.is_relative_to(root) else None


def note_path(config, note_id):
    root = config["notes_dir"]
    path = inside(root / note_id, root)
    if path is None:
        return None
    vault = config.get("vault_root")
    base = vault if vault and path.is_relative_to(vault) else root
    parts = path.relative_to(base).parts
    return None if parts and parts[0].casefold() == "checkpoints" else path


def read_note(path):
    if not path or path.suffix.lower() != ".md" or not path.is_file() or path.stat().st_size > 1_048_576:
        return {}, ""
    return metadata(path.read_text(encoding="utf-8-sig"))


class MediaLookup:
    def __init__(self, config):
        self.notes = config["notes_dir"]
        self.previews = config["previews_dir"]
        self.thumbnails = config["thumbnails_dir"]
        self.vault = config.get("vault_root")

    @staticmethod
    def _find(candidates, root):
        for candidate in candidates:
            if candidate.suffix.lower() in IMAGE_TYPES:
                image = inside(candidate, root)
                if image and image.is_file():
                    return image
        return None

    @cached_property
    def preview_names(self):
        names = defaultdict(list)
        for path in self.previews.rglob("*"):
            if path.suffix.lower() in IMAGE_TYPES and path.is_file():
                names[path.name.casefold()].append(path)
        return names

    @cached_property
    def thumbnail_names(self):
        names = defaultdict(list)
        for path in self.thumbnails.rglob("*"):
            match = re.fullmatch(r"(.+)_[0-9a-f]{8}\.jpg", path.name, re.I)
            if match and path.is_file():
                names[match[1].casefold()].append(path)
        return names

    def _linked_preview(self, path, link, wiki):
        raw = normalize_vault_path(link)
        if re.match(r"^[A-Za-z]:/", raw):
            return self._find((Path(raw),), self.previews)

        try:
            url = urlsplit(raw)
        except ValueError:
            return None
        if url.scheme == "file":
            prefix = f"//{url.netloc}" if url.netloc and url.netloc != "localhost" else ""
            return self._find((Path(url2pathname(prefix + url.path)),), self.previews)
        if url.scheme or url.netloc:
            return None

        # Wiki links may contain literal #, ? or percent characters in a filename.
        names = (raw, unquote(raw), unquote(url.path)) if wiki else (unquote(url.path),)
        for name in dict.fromkeys(names):
            if Path(name).suffix.lower() not in IMAGE_TYPES:
                continue
            name = name.lstrip("/")
            candidates = [path.parent / name, self.previews / name]
            if self.vault and (wiki or not name.startswith(("./", "../"))):
                candidates.insert(0, self.vault / name)
            parts = Path(name).parts
            candidates.extend(self.previews.joinpath(*parts[index:]) for index in range(1, len(parts)) if parts[index] != "..")
            image = self._find(candidates, self.previews)
            if image:
                return image
            matches = self.preview_names[Path(name).name.casefold()]
            if len(matches) == 1:
                return self._find(matches, self.previews)
        return None

    def preview(self, path, body):
        for match in EMBED.finditer(body):
            wiki = match[1] is not None
            link = (match[1].split("|", 1)[0] if wiki else match[2]).strip().strip("<>")
            result = self._linked_preview(path, link, wiki)
            if result:
                return result

        # Older notes can omit the embed. The importer numbers originals from 001.
        if not EMBED.search(body):
            stem = path.stem.casefold()
            matches = [
                image for suffix in IMAGE_TYPES for separator in ("", ".")
                for image in self.preview_names[f"{stem}{separator}001{suffix}"]
            ]
            if len(matches) == 1:
                return self._find(matches, self.previews)
        return None

    @cached_property
    def note_stems(self):
        return Counter(legacy_stem(path.name).casefold() for path in self.notes.rglob("*.md"))

    def thumbnail(self, path):
        # Exact hashes take precedence over a filename-only match.
        roots = dict.fromkeys((self.vault, self.notes, self.notes.parent))
        names = []
        for root in roots:
            if root is not None and path.is_relative_to(root):
                relative = path.relative_to(root).as_posix()
                names.extend((thumb_cache_name_from_md_path(relative), vault_thumb_name(relative)))
        for name in dict.fromkeys(names):
            match = self._find((
                self.thumbnails / name,
                self.thumbnails / "lora_thumb_cache" / name,
            ), self.thumbnails)
            if match:
                return match

        legacy = legacy_stem(path.name).casefold()
        obsidian = vault_thumb_name(path.name).rsplit("_", 1)[0].casefold()
        matches = [image for stem in dict.fromkeys((legacy, obsidian)) for image in self.thumbnail_names[stem]]
        for name in names:
            matching = [image for image in matches if image.name.casefold() == name.casefold()]
            if len(matching) == 1:
                return self._find(matching, self.thumbnails)
        if len(matches) == 1 and self.note_stems[legacy] == 1:
            return self._find(matches, self.thumbnails)
        return None


def rows(config):
    root = config["notes_dir"]
    lookup = MediaLookup(config)
    for path in sorted(root.rglob("*.md")):
        try:
            item = note_path(config, path.relative_to(root).as_posix())
            fields, body = read_note(item)
            if not fields.get("lora_name"):
                continue
            modified = item.stat().st_mtime_ns // 1_000_000
            thumbnail = lookup.thumbnail(item)
            preview = lookup.preview(item, body)
        except (OSError, UnicodeError):
            continue
        yield {
            "id": path.relative_to(root).as_posix(),
            "title": path.stem,
            **{key: fields.get(key, "") for key in FIELDS},
            "modified": modified,
            "thumbnail": bool(thumbnail),
            "preview": bool(preview),
            "image_reference": bool(EMBED.search(body)),
        }


def media(config, note_id, kind):
    if kind not in {"thumbnail", "preview", "note"}:
        return None
    path = note_path(config, note_id)
    fields, body = read_note(path)
    if not fields.get("lora_name"):
        return None
    if kind == "note":
        return path, "text/plain; charset=utf-8"
    lookup = MediaLookup(config)
    image = lookup.thumbnail(path) if kind == "thumbnail" else lookup.preview(path, body)
    if not image or image.suffix.lower() not in IMAGE_TYPES:
        return None
    return image, IMAGE_TYPES[image.suffix.lower()]
