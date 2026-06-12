from PIL import Image

source = "control_explorer_icon.png"
target = "control_explorer.ico"

sizes = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]

img = Image.open(source).convert("RGBA")

# Optional: sicherstellen, dass das Bild quadratisch ist
if img.width != img.height:
    min_side = min(img.width, img.height)
    left = (img.width - min_side) // 2
    top = (img.height - min_side) // 2
    img = img.crop((left, top, left + min_side, top + min_side))

img.save(target, format="ICO", sizes=sizes)

print(f"ICO gespeichert als: {target}")
print(f"Enthaltene Größen: {sizes}")