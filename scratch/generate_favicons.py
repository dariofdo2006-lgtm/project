import os
from PIL import Image, ImageDraw

def generate_favicons():
    # Target directory is the 'static' folder
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    os.makedirs(static_dir, exist_ok=True)

    # We will generate a 64x64 base image
    img = Image.new("RGBA", (64, 64), (10, 10, 11, 255)) # #0A0A0B
    draw = ImageDraw.Draw(img)
    
    # Outer rounded rect border: fill #121214, stroke #3B82F6, width 3
    draw.rounded_rectangle(
        [(12, 14), (52, 52)],
        radius=9,
        fill=(18, 18, 20, 255), # #121214
        outline=(59, 130, 246, 255), # #3B82F6
        width=3
    )
    
    # Draw vertical rings (lines) at top: x=21 and x=43 from y=10 to y=20
    draw.line([(21, 10), (21, 20)], fill=(147, 197, 253, 255), width=4) # #93C5FD
    draw.line([(43, 10), (43, 20)], fill=(147, 197, 253, 255), width=4) # #93C5FD
    
    # Draw dark grey horizontal line at y=28: from x=18 to x=46
    draw.line([(18, 28), (46, 28)], fill=(39, 39, 42, 255), width=3) # #27272A
    
    # Draw green line path: (20,43) -> (25,35) -> (30,48) -> (36,37) -> (39,31) -> (42,31) -> (46,34)
    points = [(20, 43), (25, 35), (30, 48), (36, 37), (39, 31), (42, 31), (46, 34)]
    draw.line(points, fill=(16, 185, 129, 255), width=4, joint="round") # #10B981
    
    # Draw green circles at endpoints
    draw.ellipse([(20-3, 43-3), (20+3, 43+3)], fill=(16, 185, 129, 255))
    draw.ellipse([(46-3, 34-3), (46+3, 34+3)], fill=(16, 185, 129, 255))
    
    # Save as 32x32, 16x16 PNG, and multi-size ICO
    img_32 = img.resize((32, 32), Image.Resampling.LANCZOS)
    img_16 = img.resize((16, 16), Image.Resampling.LANCZOS)
    img_48 = img.resize((48, 48), Image.Resampling.LANCZOS)
    
    img_32.save(os.path.join(static_dir, "favicon-32x32.png"))
    img_16.save(os.path.join(static_dir, "favicon-16x16.png"))
    img.save(os.path.join(static_dir, "favicon.ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print("Favicons successfully generated!")

if __name__ == "__main__":
    generate_favicons()
