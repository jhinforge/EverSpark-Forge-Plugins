import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from everspark_lora_panel import catalog, importer


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+RWxkAAAAASUVORK5CYII=")


class PanelImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = {name: self.root / name for name in ("notes_dir", "previews_dir", "thumbnails_dir", "temp_dir")}
        self.payload = {
            "title": "新模型",
            "fields": {"lora_name": "新模型", "category": "画风", "notes": '第一行\n第二行\\路径 "原文"'},
            "images": [{"data": base64.b64encode(PNG).decode("ascii")}],
        }

    def test_manual_import_updates_catalog_and_preserves_existing_note(self):
        result = importer.commit(self.config, self.payload)
        self.assertEqual(result["note"], "画风/新模型.md")
        row, = catalog.rows(self.config)
        self.assertEqual(row["notes"], self.payload["fields"]["notes"])
        self.assertEqual(row["preview_count"], 1)
        image, _ = catalog.media(self.config, row["id"], "preview")
        self.assertEqual(image.name, "新模型001.png")
        original = (self.config["notes_dir"] / result["note"]).read_bytes()
        with self.assertRaisesRegex(ValueError, "md 已存在"):
            importer.commit(self.config, self.payload)
        self.assertEqual((self.config["notes_dir"] / result["note"]).read_bytes(), original)
        self.assertEqual(list(self.config["temp_dir"].iterdir()), [])

    def test_civitai_fetches_requested_version_and_only_lists_supported_images(self):
        data = {"name": "Example: style", "modelVersions": [
            {"id": 1, "name": "old"},
            {"id": 2, "name": "new", "trainedWords": ["style"], "images": [
                {"url": "https://image.civitai.com/example.png"}, {"url": "https://example.org/other.png"},
            ]},
        ]}
        with patch.object(importer.civitai, "fetch_model_data", return_value=data) as request:
            result = importer.fetch_fields("https://civitai.com/models/9?modelVersionId=2", "test-key")
        request.assert_called_once_with("9", "test-key")
        self.assertEqual(result["title"], "Example_ style")
        self.assertEqual(result["fields"]["lora_version"], "new")
        self.assertEqual(result["previews"], ["https://image.civitai.com/example.png"])
        self.assertNotIn("test-key", str(result))

    def test_bad_images_are_rejected_before_any_archive_write(self):
        self.payload["images"] = [{"data": base64.b64encode(b"not an image").decode()}]
        with self.assertRaisesRegex(ValueError, "PNG"):
            importer.commit(self.config, self.payload)
        self.assertFalse(self.config["notes_dir"].exists())
        self.assertFalse(self.config["previews_dir"].exists())


if __name__ == "__main__":
    unittest.main()
