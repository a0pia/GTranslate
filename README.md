# GTranslate - Real-time Screen Translation Tool 🌍

**GTranslate** is a modern, high-performance tool for macOS that captures and translates on-screen text (games, videos, documents) in real-time. Built with a sleek "Midnight Gold" aesthetic, it feels like a native part of your macOS workspace.

[Türkçe Versiyon (Turkish Version)](README_TR.md)

---

## 🚀 Key Features

- **Apple Vision OCR:** High-accuracy text recognition using native macOS AI.
- **Real-time Translation:** Instant results powered by Google Translate (via deep-translator).
- **Premium UI:** "Midnight Gold" dark mode design with smooth animations.
- **Smart Auto-Hide:** Automatically retracts to the menu bar when focus is lost.
- **Translation Log:** Persistent panel to track dialogue history with speaker color-coding.
- **Pin Capability:** Keep the translation log "Always on Top" with a single click.

---

## 🛠 Installation & Setup

### 1. Clone the Project
Open your terminal and run:
```bash
git clone https://github.com/a0pia/GTranslate.git
cd GTranslate
```

### 2. Prerequisites
- macOS (Required for Apple Vision API)
- Python 3.9+

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🏃 Running the App

To start the application:
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

## 📋 Usage Guide

1.  **Select Window:** Pick the application window you want to translate.
2.  **Pick Region:** Click "Pick Region" and draw a rectangle over the area you want to scan.
3.  **Start:** Select your target language and click "Start Translation".
4.  **Pro Tip:** Click anywhere outside the menu to hide it. Use the "Pin" button on the log panel to keep your translations visible while you play or work.

---

## 📄 License
This project is licensed under the **MIT License**.

---

*Developed by: [a0pia](https://github.com/a0pia)*
