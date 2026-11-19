"""Read the LoRA Vault formats written by the existing import scripts."""

import json
import re
import shlex
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from .thumbnail_names import thumb_cache_name_from_md_path

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
    return inside(config["notes_dir"] / note_id, config["notes_dir"])


def read_note(path):
    if not path or path.suffix.lower() != ".md" or not path.is_file() or path.stat().st_size > 1_048_576:
        return {}, ""
    return metadata(path.read_text(encoding="utf-8-sig"))


def preview_path(config, path, body):
    root = config["previews_dir"]
    vault = config.get("vault_root")
    for match in EMBED.finditer(body):
        link = (match[1] or match[2]).split("|", 1)[0].strip().strip("<>")
        url = urlsplit(link)
        if url.scheme == "file":
            prefix = f"//{url.netloc}" if url.netloc and url.netloc != "localhost" else ""
            candidates = [Path(url2pathname(prefix + url.path))]
        elif not url.scheme and not url.netloc:
            relative = unquote(url.path)
            candidates = [path.parent / relative, root / relative]
            if vault and (match[1] or not relative.startswith(("./", "../"))):
                candidates.insert(0, vault / relative)
            if "/" not in relative and Path(relative).suffix.lower() in IMAGE_TYPES:
                candidates.extend(sorted(root.rglob(relative)))
        else:
            continue
        for candidate in candidates:
            if candidate.suffix.lower() not in IMAGE_TYPES:
                continue
            image = inside(candidate, root)
            if image and image.is_file():
                return image
    return None


def thumbnail_path(config, path):
    root = config["thumbnails_dir"]
    vault = config.get("vault_root")
    relative = path.relative_to(vault) if vault and path.is_relative_to(vault) else path.relative_to(config["notes_dir"])
    thumbnail = inside(root / thumb_cache_name_from_md_path(relative.as_posix()), root)
    return thumbnail if thumbnail and thumbnail.is_file() else None


def rows(config):
    root = config["notes_dir"]
    for path in sorted(root.rglob("*.md")):
        try:
            item = inside(path, root)
            fields, body = read_note(item)
        except (OSError, UnicodeError):
            continue
        if not fields.get("lora_name"):
            continue
        yield {
            "id": path.relative_to(root).as_posix(),
            "title": path.stem,
            **{key: fields.get(key, "") for key in FIELDS},
            "thumbnail": bool(thumbnail_path(config, item)),
            "preview": bool(EMBED.search(body)),
        }


def media(config, note_id, kind):
    if kind not in {"thumbnail", "preview"}:
        return None
    path = note_path(config, note_id)
    fields, body = read_note(path)
    if not fields.get("lora_name"):
        return None
    image = thumbnail_path(config, path) if kind == "thumbnail" else preview_path(config, path, body)
    if not image or image.suffix.lower() not in IMAGE_TYPES:
        return None
    return image, IMAGE_TYPES[image.suffix.lower()]
