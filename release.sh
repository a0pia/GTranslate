#!/bin/bash
# GTranslate - Release & DMG Creator Script
# TR: Bu script uygulamayı derler ve kurulum için bir DMG dosyası oluşturur.
# EN: This script builds the app and creates a DMG file for distribution.

APP_NAME="GTranslate"
SPEC_FILE="GTranslate.spec"
DMG_NAME="GTranslate_Installer.dmg"

echo "------------------------------------------------"
echo "1. Uygulama Derleniyor / Building App..."
echo "------------------------------------------------"

# Temizlik / Cleanup
rm -rf build dist "$DMG_NAME"

# Derleme / Build
./venv/bin/pyinstaller "$SPEC_FILE"

if [ ! -d "dist/$APP_NAME.app" ]; then
    echo "HATA / ERROR: Derleme başarısız oldu! / Build failed!"
    exit 1
fi

echo "------------------------------------------------"
echo "1.5 Uygulama İmzalanıyor / Codesigning App..."
echo "------------------------------------------------"
# Using a more flexible signing method for better screen capture compatibility
codesign --force --deep --sign - "dist/$APP_NAME.app"

echo "------------------------------------------------"
echo "2. DMG Dosyası Oluşturuluyor / Creating DMG..."
echo "------------------------------------------------"

# Geçici bir klasör oluştur / Create a temp folder
mkdir -p dist/dmg_tmp
cp -R "dist/$APP_NAME.app" dist/dmg_tmp/
ln -s /Applications dist/dmg_tmp/Applications

# hdiutil ile DMG oluştur / Create DMG using hdiutil
hdiutil create -volname "$APP_NAME Installer" -srcfolder dist/dmg_tmp -ov -format UDZO "$DMG_NAME"

# Temizlik / Cleanup
rm -rf dist/dmg_tmp

echo "------------------------------------------------"
echo "BAŞARILI / SUCCESS!"
echo "Kurulum dosyası hazır: $DMG_NAME"
echo "Installer is ready: $DMG_NAME"
echo "------------------------------------------------"
