"""Plan and apply a confirmed deletion inside the configured catalog."""
import hashlib
import json
from urllib.parse import unquote
from uuid import uuid4

from .catalog import MediaLookup, inside, note_path, read_note


def _files_for(config, note_id):
    root = config["notes_dir"]
    if not isinstance(note_id, str) or not note_id or len(note_id) > 4096:
        raise ValueError("无效的 LoRA 笔记。")
    path = note_path(config, note_id)
    if path is None or path.relative_to(root).as_posix() != note_id:
        raise FileNotFoundError("LoRA 笔记不存在。")
    fields, body = read_note(path)
    if not fields.get("lora_name"):
        raise FileNotFoundError("LoRA 笔记不存在。")

    lookup = MediaLookup(config)
    previews = set(lookup.previews_for(path, body))
    keys = {key.casefold() for key in lookup.thumbnail_keys(path)}
    thumbnails = set()
    if lookup.thumbnails.is_dir():
        for candidate in lookup.thumbnails.rglob("*"):
            if candidate.name.casefold() in keys:
                resolved = inside(candidate, lookup.thumbnails)
                if resolved and resolved.is_file() and not candidate.is_symlink():
                    thumbnails.add(resolved)

    # Check the whole configured Vault as well as any notes outside that Vault.
    vault = config.get("vault_root")
    roots = [vault] if vault and root.is_relative_to(vault) else [root, vault]
    retained = set()
    ambiguous_caches = set()
    for scan_root in dict.fromkeys(filter(None, roots)):
        for other in scan_root.rglob("*.[mM][dD]"):
            if not other.is_file():
                continue
            resolved = inside(other, scan_root)
            if not resolved or other == path:
                continue
            if previews:
                try:
                    raw = other.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeError):
                    # An unreadable note may still own a preview.
                    retained.update(previews)
                    previews.clear()
                else:
                    decoded = unquote(raw).casefold()
                    folded = raw.casefold()
                    retained.update(image for image in previews if image.name.casefold() in folded
                                    or image.name.casefold() in decoded)
                    if other.stem.casefold() == path.stem.casefold():
                        # A legacy note can use the same numbered files without embeds.
                        retained.update(previews)
                    previews.difference_update(retained)
            if thumbnails and resolved.is_relative_to(root):
                other_keys = {key.casefold() for key in lookup.thumbnail_keys(resolved)}
                ambiguous_caches.update(image for image in thumbnails if image.name.casefold() in other_keys)
                thumbnails.difference_update(ambiguous_caches)

    cache = lookup.thumbnail(path)
    if cache and cache not in thumbnails:
        ambiguous_caches.add(cache)
    # A file may be both a referenced preview and a cache when directories overlap.
    previews.difference_update(retained)
    thumbnails.difference_update(retained | previews)
    targets = [path, *sorted(previews), *sorted(thumbnails)]
    snapshots = []
    for file in targets:
        stat = file.stat()
        snapshots.append((str(file), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    plan = {
        "name": fields["lora_name"],
        "notes": 1,
        "previews": len(previews),
        "thumbnails": len(thumbnails),
        "kept_previews": len(retained),
        "kept_thumbnails": len(ambiguous_caches | (retained & {cache})),
    }
    plan["token"] = hashlib.sha256(json.dumps((plan, snapshots)).encode("utf-8")).hexdigest()
    return plan, targets


def preview(config, note_id):
    plan, _ = _files_for(config, note_id)
    return plan


def commit(config, note_id, token):
    plan, targets = _files_for(config, note_id)
    if token != plan["token"]:
        raise ValueError("待删文件已变化，请重新打开确认窗口。")

    staged = []
    try:
        for file in targets:
            temporary = file.with_name(f".lora-delete-{uuid4().hex}.pending")
            file.rename(temporary)
            staged.append((file, temporary))
    except OSError as exc:
        recovery = []
        for file, temporary in reversed(staged):
            try:
                if file.exists() or file.is_symlink():
                    raise FileExistsError(file)
                temporary.rename(file)
            except OSError:
                recovery.append(str(temporary))
        if recovery:
            raise ValueError("删除中止，以下文件需手动恢复：" + "、".join(recovery)) from exc
        raise ValueError("无法移走待删文件，已恢复本次改动。请检查文件是否被占用。") from exc

    remaining = []
    for _, temporary in staged:
        try:
            temporary.unlink()
        except OSError:
            remaining.append(str(temporary))
    return {"remaining": remaining}
