#!/bin/bash
# TR: icon.png dosyasini macOS .icns formatina donusturur.
# EN: Converts icon.png to macOS .icns format.

if [ ! -f "icon.png" ]; then
    echo "HATA: icon.png bulunamadi!"
    exit 1
fi

mkdir -p icon.iconset

# Farkli boyutlari olustur / Create different sizes
sips -s format png -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -s format png -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -s format png -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -s format png -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -s format png -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -s format png -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -s format png -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -s format png -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -s format png -z 512 512   icon.png --out icon.iconset/icon_512x512.png
cp icon.png icon.iconset/icon_512x512@2x.png

# .icns dosyasini birlestir / Assemble .icns
iconutil -c icns icon.iconset

# Temizlik / Cleanup
rm -rf icon.iconset

echo "BASARILI: icon.icns olusturuldu."
