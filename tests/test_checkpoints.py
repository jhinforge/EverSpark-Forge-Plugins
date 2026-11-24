import importlib.util
import tempfile
import unittest
from pathlib import Path

from everspark_lora_panel import catalog, thumbnail_rebuild


class CheckpointsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.vault = Path(temp.name)

    def config(self, library, notes):
        paths = {"notes_dir": self.vault / notes, "previews_dir": self.vault / (library + "-images"),
                 "thumbnails_dir": self.vault / (library + "-cache"), "temp_dir": self.vault / (library + "-temp")}
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return {**paths, "vault_root": self.vault, "library": library}

    def test_checkpoint_uses_native_fields_and_its_own_media(self):
        cfg = self.config("checkpoints", "Checkpoints")
        note = cfg["notes_dir"] / "model.md"
        note.write_text("---\nmodel_name: Model\nbase_model: SDXL\nstyle: Ink\ntested: true\nPOSITIVE: >-\n  sharp detail\nNEGATIVE: noise\n---\n![[preview.png]]", encoding="utf-8")
        img = cfg["previews_dir"] / "preview.png"
        img.write_bytes(b"fixture")
        item, = catalog.rows(cfg)
        self.assertEqual((item["model_name"], item["base_model"], item["style"], item["POSITIVE"], item["NEGATIVE"]),
                         ("Model", "SDXL", "Ink", "sharp detail", "noise"))
        self.assertEqual(item["category"], "")
        self.assertEqual(catalog.media(cfg, "model.md", "preview"), (img, "image/png"))
        self.assertEqual(catalog.media(cfg, "model.md", "note"), (note, "text/plain; charset=utf-8"))
        lora = {**cfg, "library": "lora", "notes_dir": self.vault}
        self.assertFalse(list(catalog.rows(lora)))
        self.assertIsNone(catalog.media(lora, "Checkpoints/model.md", "note"))

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow required to check actual encoding")
    def test_rebuild_isolated_by_library_and_retains_cache_for_failed_image(self):
        from PIL import Image
        lora = self.config("lora", "LoRA")
        checkpoint = self.config("checkpoints", "Checkpoints")
        for cfg, field in ((lora, "lora_name"), (checkpoint, "model_name")):
            (cfg["notes_dir"] / "model.md").write_text(f"---\n{field}: Model\n---\n![[first.png]]\n![[second.png]]", encoding="utf-8")
            Image.new("RGBA", (600, 300), (30, 60, 90, 180)).save(cfg["previews_dir"] / "first.png")
        self.assertEqual(thumbnail_rebuild.rebuild(checkpoint), {"generated": 1, "missing": 0, "failed": 0})
        self.assertEqual(list(lora["thumbnails_dir"].iterdir()), [])
        out, _ = catalog.media(checkpoint, "model.md", "thumbnail")
        previous = out.read_bytes()
        with Image.open(out) as image:
            self.assertEqual((image.format, image.size), ("JPEG", (420, 210)))
        (checkpoint["previews_dir"] / "first.png").write_bytes(b"bad image")
        self.assertEqual(thumbnail_rebuild.rebuild(checkpoint)["failed"], 1)
        self.assertEqual(out.read_bytes(), previous)
        self.assertEqual(thumbnail_rebuild.rebuild(lora)["generated"], 1)
        self.assertEqual(list(checkpoint["temp_dir"].iterdir()), [])
        self.assertEqual(list(lora["temp_dir"].iterdir()), [])
