"""Generate the project's original audio-routing icon (requires Pillow)."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

output = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else (Path(__file__).resolve().parents[1] / "custom_components/dm_nax/brand")
)
output.mkdir(parents=True, exist_ok=True)
image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((64, 64, 960, 960), radius=120, fill="#153F3B")
draw.line((472, 512, 648, 512), fill="#FBFAF5", width=28)
draw.line((648, 274, 648, 750), fill="#FBFAF5", width=28)
for y in (274, 512, 750):
    draw.line((648, y, 756, y), fill="#FBFAF5", width=28)
    draw.ellipse((714, y - 42, 798, y + 42), fill="#7EE6B0")
draw.rounded_rectangle((202, 270, 480, 754), radius=24, fill="#FBFAF5")
draw.ellipse((278, 328, 404, 454), fill="#153F3B")
draw.ellipse((254, 510, 428, 684), fill="#153F3B")
draw.ellipse((301, 557, 381, 637), fill="#7EE6B0")
for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
    image.resize((size, size), Image.Resampling.LANCZOS).save(
        output / name, optimize=True
    )
