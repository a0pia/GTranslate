from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # 1024x1024 transparent image
    img = Image.new('RGBA', (1024, 1024), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # Try to find a bold macOS system font
    font_paths = [
        '/System/Library/Fonts/SFNS.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
    ]
    
    font = None
    for path in font_paths:
        if os.path.exists(path):
            try:
                # Use index 1 or try to load a specific bold variation if it's a TTC
                font = ImageFont.truetype(path, 800, index=1) # Often index 1 is Bold in TTC
                break
            except:
                try:
                    font = ImageFont.truetype(path, 800)
                    break
                except:
                    continue
    
    if font is None:
        font = ImageFont.load_default()
        
    # Draw white G in the middle
    draw.text((512, 512), "G", fill="white", anchor="mm", font=font)
    
    img.save("icon.png")
    print("icon.png created successfully.")

if __name__ == "__main__":
    create_icon()
