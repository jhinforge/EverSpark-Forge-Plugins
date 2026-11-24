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


CHECKPOINT_FIELDS = ("model_name", "base_model", "model_version", "category", "style",
                     "tested", "download_url", "notes", "POSITIVE", "NEGATIVE")


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
    if config.get("library") != "checkpoints" and parts and parts[0].casefold() == "checkpoints":
        return None
    return path


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

    @cached_property
    def numbered_previews(self):
        by_stem = defaultdict(lambda: defaultdict(list))
        for filename, paths in self.preview_names.items():
            match = re.fullmatch(r"(.+?)(?:\.)?([0-9]{3})", Path(filename).stem)
            if match:
                stem, number = match.groups()
                by_stem[stem][int(number)].extend(paths)
        return by_stem

    def previews_for(self, path, body):
        embeds = list(EMBED.finditer(body))
        seen = set()
        for match in embeds:
            wiki = match[1] is not None
            link = (match[1].split("|", 1)[0] if wiki else match[2]).strip().strip("<>")
            image = self._linked_preview(path, link, wiki)
            if image and image not in seen:
                seen.add(image)
                yield image

        # Older notes can omit embeds and use numbered image names instead.
        if not embeds:
            for _, candidates in sorted(self.numbered_previews[path.stem.casefold()].items()):
                if len(candidates) == 1:
                    image = self._find(candidates, self.previews)
                    if image:
                        yield image

    @cached_property
    def note_stems(self):
        return Counter(legacy_stem(path.name).casefold() for path in self.notes.rglob("*.md"))

    def thumbnail_keys(self, path):
        roots = dict.fromkeys((self.vault, self.notes, self.notes.parent))
        names = []
        for root in roots:
            if root is not None and path.is_relative_to(root):
                relative = path.relative_to(root).as_posix()
                names.extend((thumb_cache_name_from_md_path(relative), vault_thumb_name(relative)))
        return list(dict.fromkeys(names))

    def thumbnail(self, path):
        names = self.thumbnail_keys(path)
        for name in names:
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


def entries(config):
    root = config["notes_dir"]
    name = "model_name" if config.get("library") == "checkpoints" else "lora_name"
    for path in sorted(root.rglob("*.md")):
        try:
            item = note_path(config, path.relative_to(root).as_posix())
            fields, body = read_note(item)
        except (OSError, UnicodeError):
            continue
        if fields.get(name):
            yield item, fields, body


def rows(config):
    root = config["notes_dir"]
    checkpoint = config.get("library") == "checkpoints"
    lookup = MediaLookup(config)
    for item, fields, body in entries(config):
        try:
            modified = item.stat().st_mtime_ns // 1_000_000
            thumbnail = lookup.thumbnail(item)
            preview_count = sum(1 for _ in lookup.previews_for(item, body))
        except (OSError, UnicodeError):
            continue
        yield {
            "id": item.relative_to(root).as_posix(),
            "title": item.stem,
            **{key: fields.get(key, "") for key in (CHECKPOINT_FIELDS if checkpoint else FIELDS)},
            "modified": modified,
            "thumbnail": bool(thumbnail),
            "preview": preview_count > 0,
            "preview_count": preview_count,
            "image_reference": bool(EMBED.search(body)),
        }


def media(config, note_id, kind):
    indexed = re.fullmatch(r"preview:([0-9]{1,6})", kind)
    if kind not in {"thumbnail", "preview", "note"} and not indexed:
        return None
    path = note_path(config, note_id)
    fields, body = read_note(path)
    if not fields.get("model_name" if config.get("library") == "checkpoints" else "lora_name"):
        return None
    if kind == "note":
        return path, "text/plain; charset=utf-8"
    lookup = MediaLookup(config)
    if kind == "thumbnail":
        image = lookup.thumbnail(path)
    else:
        index = int(indexed[1]) if indexed else 0
        image = next((image for number, image in enumerate(lookup.previews_for(path, body)) if number == index), None)
    if not image or image.suffix.lower() not in IMAGE_TYPES:
        return None
    return image, IMAGE_TYPES[image.suffix.lower()]
