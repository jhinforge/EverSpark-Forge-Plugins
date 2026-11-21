import tempfile
import unittest
from pathlib import Path

from everspark_lora_panel.catalog import media, rows
from everspark_lora_panel.thumbnail_names import thumb_cache_name_from_md_path, vault_thumb_name


class MediaTests(unittest.TestCase):
    def setUp(self):
        sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(sandbox.cleanup)
        self.vault = Path(sandbox.name)
        self.notes = self.vault / "lora"
        self.previews = self.vault / "Assets" / "Loras"
        self.thumbnails = self.vault / "temp" / "lora_thumb_cache"
        self.config = {
            "notes_dir": self.notes,
            "previews_dir": self.previews,
            "thumbnails_dir": self.thumbnails,
        }

    def write(self, path, content="image"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def note(self, embed="", name="服装/kiss.md"):
        return self.write(self.notes / name, "---\nlora_name: kiss\n---\n" + embed)

    def test_vault_relative_embed_works_with_parent_or_numbered_folder(self):
        self.note(r"![[Assets\Loras\002\kiss001.png|250]]")
        original = self.write(self.previews / "002" / "kiss001.png")
        for folder in (self.previews, original.parent):
            with self.subTest(folder=folder):
                config = {**self.config, "previews_dir": folder}
                self.assertTrue(next(rows(config))["preview"])
                self.assertEqual(media(config, "服装/kiss.md", "preview"), (original, "image/png"))

    def test_embeds_support_spaces_and_literal_hashes(self):
        self.note("![[Assets/Loras/001/kiss #1.jpg|300]]")
        original = self.write(self.previews / "001" / "kiss #1.jpg")
        self.assertEqual(media(self.config, "服装/kiss.md", "preview")[0], original)
        self.note("![](<../../Assets/Loras/001/kiss%20%231.jpg>)")
        self.assertEqual(media(self.config, "服装/kiss.md", "preview")[0], original)

    def test_no_embed_can_use_unique_numbered_original(self):
        self.note()
        image = self.write(self.previews / "001" / "kiss.001.jpeg")
        self.assertEqual(media(self.config, "服装/kiss.md", "preview")[0], image)
        self.write(self.previews / "002" / "kiss.001.jpeg")
        self.assertIsNone(media(self.config, "服装/kiss.md", "preview"))

    def test_gallery_follows_note_order_and_skips_duplicates_and_missing_images(self):
        jpg = self.write(self.previews / "001" / "kiss001.jpg")
        png = self.write(self.previews / "002" / "kiss.002.png")
        self.note("![[Assets/Loras/002/kiss.002.png]]\n![[missing.png]]\n"
                  "![](Assets/Loras/001/kiss001.jpg)\n![[kiss.002.png]]")
        note = "服装/kiss.md"
        self.assertEqual(next(rows(self.config))["preview_count"], 2)
        self.assertEqual(media(self.config, note, "preview"), (png, "image/png"))
        self.assertEqual(media(self.config, note, "preview:0"), (png, "image/png"))
        self.assertEqual(media(self.config, note, "preview:1"), (jpg, "image/jpeg"))
        self.assertIsNone(media(self.config, note, "preview:2"))
        self.assertIsNone(media(self.config, note, "preview:-1"))

    def test_gallery_falls_back_to_numbered_files_order(self):
        self.note()
        second = self.write(self.previews / "002" / "kiss002.png")
        first = self.write(self.previews / "001" / "kiss.001.jpg")
        self.write(self.previews / "001" / "kiss_other003.jpg")
        note = "服装/kiss.md"
        self.assertEqual(next(rows(self.config))["preview_count"], 2)
        self.assertEqual(media(self.config, note, "preview:0")[0], first)
        self.assertEqual(media(self.config, note, "preview:1")[0], second)

    def test_unavailable_original_is_not_advertised(self):
        outside = self.write(self.vault / "outside.png")
        self.note(f"![]({outside.as_uri()})")
        self.assertFalse(next(rows(self.config))["preview"])
        self.assertIsNone(media(self.config, "服装/kiss.md", "preview"))
        self.assertIsNone(media(self.config, "../outside.png", "preview"))

    def test_catalog_reports_modified_time_and_unresolved_embedding(self):
        note = self.note("![[missing.png]]")
        row = next(rows(self.config))
        self.assertEqual(row["modified"], note.stat().st_mtime_ns // 1_000_000)
        self.assertTrue(row["image_reference"])
        self.assertFalse(row["preview"])

    def test_note_media_is_read_only_and_limited_to_catalog_notes(self):
        note = self.note("![[example.png]]")
        self.assertEqual(media(self.config, "服装/kiss.md", "note"), (note, "text/plain; charset=utf-8"))
        self.note(name="Checkpoints/kiss.md")
        self.assertIsNone(media(self.config, "Checkpoints/kiss.md", "note"))
        self.assertEqual(len(list(rows(self.config))), 1)
        self.write(self.vault / "outside.md", note.read_text(encoding="utf-8"))
        self.write(self.notes / "not-a-model.md")
        self.assertIsNone(media(self.config, "../outside.md", "note"))
        self.assertIsNone(media(self.config, "not-a-model.md", "note"))

    def test_thumbnail_uses_exact_hash_before_legacy_fallback(self):
        self.note()
        exact = self.write(self.thumbnails / thumb_cache_name_from_md_path("lora/服装/kiss.md"))
        duplicate = self.write(self.thumbnails / "kiss_01234567.jpg")
        self.assertEqual(media(self.config, "服装/kiss.md", "thumbnail")[0], exact)
        exact.unlink()
        self.assertEqual(media(self.config, "服装/kiss.md", "thumbnail")[0], duplicate)
        extra_note = self.note(name="画风/kiss.md")
        self.assertIsNone(media(self.config, "服装/kiss.md", "thumbnail"))
        extra_note.unlink()
        self.write(self.thumbnails / "kiss_12345678.jpg")
        self.assertIsNone(media(self.config, "服装/kiss.md", "thumbnail"))

    def test_obsidian_utf16_hash_from_numbered_category_root(self):
        self.note(name="✨/kiss.md")
        directory = self.notes / "✨"
        config = {**self.config, "notes_dir": directory, "vault_root": self.vault}
        name = vault_thumb_name("lora/✨/kiss.md")
        self.assertEqual(name, thumb_cache_name_from_md_path("lora/✨/kiss.md"))
        self.note(name="😀/kiss.md")
        config["notes_dir"] = self.notes / "😀"
        name = vault_thumb_name("lora/😀/kiss.md")
        self.assertNotEqual(name, thumb_cache_name_from_md_path("lora/😀/kiss.md"))
        root = self.vault / "temp"
        original = self.write(self.thumbnails / name)
        config["thumbnails_dir"] = root
        self.assertEqual(media(config, "kiss.md", "thumbnail")[0], original)


if __name__ == "__main__":
    unittest.main()
