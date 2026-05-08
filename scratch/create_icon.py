from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # 1024x1024 Black background
    img = Image.new('RGBA', (1024, 1024), (0, 0, 0, 255))
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
                # index 1 usually is Bold in Helvetica.ttc
                # Using 900 for size and ensuring it's really bold
                font = ImageFont.truetype(path, 900, index=1)
                break
            except:
                try:
                    font = ImageFont.truetype(path, 900)
                    break
                except:
                    continue
    
    if font is None:
        font = ImageFont.load_default()
        
    # Draw white G in the middle with extra thickness
    draw.text((512, 510), "G", fill="white", anchor="mm", font=font)
    
    img.save("icon.png")
    print("icon.png created successfully.")

if __name__ == "__main__":
    create_icon()
