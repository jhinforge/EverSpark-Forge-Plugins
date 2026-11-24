import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from everspark_lora_panel import delete_entry
from everspark_lora_panel.thumbnail_names import thumb_cache_name_from_md_path


class DeleteEntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = {
            "vault_root": self.root,
            "notes_dir": self.root / "LoRA",
            "previews_dir": self.root / "images",
            "thumbnails_dir": self.root / "cache",
        }
        self.image = self.write("images/001/example001.png")
        self.shared = self.write("images/002/shared.png")
        self.note = self.write("LoRA/画风/example.md",
                               "---\nlora_name: Test LoRA\n---\n![[images/001/example001.png]]\n![[images/002/shared.png]]")
        self.other = self.write("Elsewhere/story.md", "![shared](../images/002/shared.png)")
        self.id = "画风/example.md"
        cache_name = thumb_cache_name_from_md_path("LoRA/" + self.id)
        self.thumb = self.write("cache/" + cache_name)
        self.weights = self.write("example.safetensors")

    def write(self, name, body="fixture"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_preview_then_delete_preserves_shared_previews(self):
        plan = delete_entry.preview(self.config, self.id)
        self.assertEqual([plan[key] for key in ("notes", "previews", "thumbnails", "kept_previews")], [1, 1, 1, 1])
        self.assertTrue(self.note.exists())
        self.assertEqual(delete_entry.commit(self.config, self.id, plan["token"]), {"remaining": []})
        for path in (self.note, self.image, self.thumb):
            self.assertFalse(path.exists())
        for path in (self.other, self.shared, self.weights):
            self.assertTrue(path.exists())

    def test_changed_sharing_rejects_confirmation_and_replans(self):
        plan = delete_entry.preview(self.config, self.id)
        self.other.write_text("![[example001.png]]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "已变化"):
            delete_entry.commit(self.config, self.id, plan["token"])
        self.assertTrue(self.note.is_file())
        self.assertTrue(self.image.is_file())

    def test_staging_failure_rolls_back(self):
        plan = delete_entry.preview(self.config, self.id)
        rename = Path.rename

        def fail_image(path, target):
            if path == self.image:
                raise PermissionError(path)
            return rename(path, target)

        with patch.object(Path, "rename", fail_image), self.assertRaisesRegex(ValueError, "已恢复"):
            delete_entry.commit(self.config, self.id, plan["token"])
        self.assertTrue(self.note.is_file())
        self.assertTrue(self.image.is_file())

    def test_guessed_legacy_thumbnail_is_kept(self):
        self.thumb.unlink()
        cache = self.write("cache/example_01234567.jpg")
        plan = delete_entry.preview(self.config, self.id)
        self.assertEqual(plan["thumbnails"], 0)
        self.assertEqual(plan["kept_thumbnails"], 1)
        delete_entry.commit(self.config, self.id, plan["token"])
        self.assertTrue(cache.is_file())

    def test_outside_note_cannot_be_deleted(self):
        outside = self.write("Elsewhere/outside.md", "---\nlora_name: Outside\n---\n")
        with self.assertRaises(FileNotFoundError):
            delete_entry.preview(self.config, "../Elsewhere/outside.md")
        self.assertTrue(outside.is_file())
