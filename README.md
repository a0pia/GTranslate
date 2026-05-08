# GTranslate - Real-time Screen Translation Tool 🌍

**GTranslate** is a modern, high-performance tool for macOS that captures and translates on-screen text (games, videos, documents) in real-time. Built with a sleek "Midnight Gold" aesthetic, it feels like a native part of your macOS workspace.

---

## 🇹🇷 Türkçe Açıklama

**GTranslate**, özellikle oyun severler ve yabancı dilde içerik tüketen macOS kullanıcıları için geliştirilmiş, ekran üzerindeki metinleri anlık olarak yakalayıp Türkçeye (veya seçtiğiniz diğer dillere) çeviren profesyonel bir araçtır. 

- **Hız:** Apple'ın yerel Vision OCR teknolojisi ile milisaniyeler içinde metin tanıma.
- **Şıklık:** macOS ekosistemine tam uyumlu, göz yormayan modern tasarım.
- **Kullanım Kolaylığı:** Menü çubuğundan tek tıkla erişim ve akıllı gizleme özelliği.

---

## 🚀 Key Features

- **Apple Vision OCR:** High-accuracy text recognition using native macOS AI.
- **Real-time Translation:** Instant results powered by Google Translate (via deep-translator).
- **Premium UI:** "Midnight Gold" dark mode design with smooth animations.
- **Smart Auto-Hide:** Automatically retracts to the menu bar when focus is lost.
- **Translation Log:** Persistent panel to track dialogue history with speaker color-coding.
- **Pin Capability:** Keep the translation log "Always on Top" with a single click.

---

## 🛠 Installation & Setup (Kurulum)

### 1. Clone the Project (Projeyi İndir)
Open your terminal and run / Terminali açın ve şu komutları girin:
```bash
git clone https://github.com/a0pia/GTranslate.git
cd GTranslate
```

### 2. Prerequisites (Gereksinimler)
- macOS (Required for Apple Vision API)
- Python 3.9+

### 3. Install Dependencies (Kütüphaneleri Yükle)
```bash
pip install -r requirements.txt
```

---

## 🏃 Running the App (Çalıştırma)

To start the application / Uygulamayı başlatmak için:
```bash
python3 main.py
```
Alternatively, you can double-click the `baslat.command` file in the project folder.

---

## 📦 Building a Standalone App (.app)

To package the project into a native macOS `.app`:
```bash
pyinstaller GTranslate.spec
```
The finished package will be located in the `dist/GTranslate.app` folder.

---

## 📋 Usage Guide (Kullanım Kılavuzu)

1.  **Select Window:** Pick the application window you want to translate.
2.  **Pick Region:** Click "Pick Region" and draw a rectangle over the area you want to scan.
3.  **Start:** Select your target language and click "Start Translation".
4.  **Pro Tip:** Click anywhere outside the menu to hide it. Use the "Pin" button on the log panel to keep your translations visible while you play or work.

---

## 📄 License (Lisans)
This project is licensed under the **MIT License**. 

**MIT Lisansı Nedir?**
Dünyanın en yaygın açık kaynak lisanslarından biridir. Size şu hakları verir:
- **Özgürlük:** Kodu istediğiniz gibi kullanabilir, kopyalayabilir, değiştirebilir ve satabilirsiniz.
- **Sorumluluk:** Yazılım "olduğu gibi" sunulur; herhangi bir garanti verilmez.
- **Koşul:** Lisans dosyasını ve telif hakkı bildirimini korumanız yeterlidir.

---

*Developed by: [a0pia](https://github.com/a0pia)*
