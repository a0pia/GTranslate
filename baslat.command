#!/bin/bash
# TR: Bu script uygulamayı terminal üzerinden başlatır.
# EN: This script starts the application via terminal.
# TR: Eğer .app izniyle ilgili sorun yaşarsanız bunu kullanabilirsiniz.
# EN: You can use this if you have issues with .app permissions.

cd "$(dirname "$0")"
echo "------------------------------------------------"
echo "GTranslate Başlatılıyor / Starting (Terminal)"
echo "------------------------------------------------"

# TR: Uygulama dizinine git / EN: Go to app directory
if [ -d "dist/GTranslate" ]; then
    ./dist/GTranslate/GTranslate
else
    echo "HATA / ERROR: Derlenmiş uygulama bulunamadı / Compiled app not found (dist/GTranslate)."
    echo "Lütfen önce uygulamayı derleyin / Please build first: pyinstaller GTranslate.spec"
    read -p "Çıkmak için bir tuşa basın / Press any key to exit..."
fi
