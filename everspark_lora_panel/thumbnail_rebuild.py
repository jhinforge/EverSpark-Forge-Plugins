"""Rebuild the selected library's JPEG caches from its first local previews."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from .catalog import MediaLookup, entries, inside


WINDOWS_ENCODER = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing
$jobs = [Console]::In.ReadToEnd() | ConvertFrom-Json
foreach ($job in $jobs) {
    try {
        $image = [Drawing.Image]::FromFile($job.source)
        try {
            if ($image.PropertyIdList -contains 274) {
                $orientation = $image.GetPropertyItem(274).Value[0]
                $rotation = @{2=4; 3=2; 4=6; 5=5; 6=1; 7=7; 8=3}[[int]$orientation]
                if ($null -ne $rotation) { $image.RotateFlip([Drawing.RotateFlipType]$rotation) }
            }
            $scale = [Math]::Min(1, 420 / [double][Math]::Max($image.Width, $image.Height))
            $width = [Math]::Max(1, [int]($image.Width * $scale))
            $height = [Math]::Max(1, [int]($image.Height * $scale))
            $bitmap = [Drawing.Bitmap]::new($width, $height)
            try {
                $graphics = [Drawing.Graphics]::FromImage($bitmap)
                try {
                    $graphics.Clear([Drawing.Color]::White)
                    $graphics.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                    $graphics.DrawImage($image, 0, 0, $width, $height)
                } finally { $graphics.Dispose() }
                $bitmap.Save($job.output, [Drawing.Imaging.ImageFormat]::Jpeg)
            } finally { $bitmap.Dispose() }
        } finally { $image.Dispose() }
    } catch {
        if (Test-Path -LiteralPath $job.output) { Remove-Item -LiteralPath $job.output -ErrorAction SilentlyContinue }
        [Console]::Error.WriteLine($_.Exception.Message)
    }
}
"""


def _encode(jobs):
    try:
        from PIL import Image, ImageOps
    except ImportError:
        if sys.platform != "win32":
            raise ValueError("缩略图重建需要 Pillow。请用运行客户端的 Python 安装 Pillow。") from None
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        payload = [{"source": str(src), "output": str(dst)} for src, dst, _ in jobs]
        result = subprocess.run(
            [str(executable), "-NoProfile", "-NonInteractive", "-Command", WINDOWS_ENCODER],
            input=json.dumps(payload), encoding="utf-8", capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise ValueError("无法启动 Windows 缩略图生成器。")
        return
    for source, output, _ in jobs:
        try:
            with Image.open(source) as original:
                image = ImageOps.exif_transpose(original)
                image.thumbnail((420, 420), Image.Resampling.LANCZOS)
                rgba = image.convert("RGBA")
                canvas = Image.new("RGB", rgba.size, "white")
                canvas.paste(rgba, mask=rgba.getchannel("A"))
                canvas.save(output, "JPEG", quality=86, optimize=True)
        except (OSError, ValueError, Image.DecompressionBombError):
            output.unlink(missing_ok=True)


def rebuild(config):
    lookup = MediaLookup(config)
    result = {"generated": 0, "missing": 0, "failed": 0}
    if not lookup.notes.is_dir():
        raise ValueError("笔记目录不存在。")
    config["temp_dir"].mkdir(parents=True, exist_ok=True)
    lookup.thumbnails.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="thumbnail-rebuild-", dir=config["temp_dir"]) as staging:
        jobs = []
        for note, _, body in entries(config):
            source = next(lookup.previews_for(note, body), None)
            if source is None:
                result["missing"] += 1
                continue
            target = lookup.thumbnails / lookup.thumbnail_keys(note)[0]
            if inside(target, lookup.thumbnails) is None or target == source or target.is_symlink():
                result["failed"] += 1
                continue
            jobs.append((source, Path(staging) / f"{len(jobs)}.jpg", target))
        if jobs:
            _encode(jobs)
        for _, output, target in jobs:
            if not output.is_file():
                result["failed"] += 1
                continue
            temporary = None
            try:
                with NamedTemporaryFile(dir=lookup.thumbnails, delete=False) as file:
                    temporary = Path(file.name)
                    with output.open("rb") as image:
                        shutil.copyfileobj(image, file)
                temporary.replace(target)
                result["generated"] += 1
            except OSError:
                result["failed"] += 1
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
    return result
