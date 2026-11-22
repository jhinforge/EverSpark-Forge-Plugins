"""Keep the terminal utilities' original module paths."""
from pathlib import Path

__path__.append(str(Path(__file__).resolve().parents[1] / "everspark_lora_panel" / "import_tools"))
