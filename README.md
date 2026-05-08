# GTranslate - Real-time Screen Translation Tool 🌍

**GTranslate**, macOS işletim sistemi için geliştirilmiş, ekran üzerindeki metinleri (oyunlar, videolar, dokümanlar) gerçek zamanlı olarak yakalayıp istediğiniz dile çeviren modern ve şık bir araçtır.

---

## 🚀 Özellikler / Features

- **Apple Vision OCR:** macOS'in yerleşik yapay zekasını kullanarak yüksek doğrulukta metin tanıma.
- **Gerçek Zamanlı Çeviri:** Google Translate (deep-translator) altyapısı ile anlık çeviri.
- **Modern Arayüz:** "Midnight Gold" temalı, macOS yerel uygulaması hissi veren tasarım.
- **Akıllı Gizleme (Auto-Hide):** Menü çubuğu odağı kaybettiğinde otomatik olarak gizlenir.
- **Çeviri Günlüğü (Log Panel):** Geçmiş çevirileri renk kodları ve konuşmacı ayrımı ile takip edin.
- **Sabitleme (Pin):** Günlük panelini ekranın istediğiniz yerinde her zaman üstte tutun.

---

## 🛠 Kurulum / Installation

### 1. Gereksinimler / Prerequisites
- macOS (Apple Vision API desteği için)
- Python 3.9+

### 2. Kütüphaneleri Yükle / Install Dependencies
Terminal üzerinden şu komutu çalıştırın:
```bash
pip install -r requirements.txt
```

---

## 🏃 Çalıştırma / Running

Uygulamayı başlatmak için:
```bash
python3 main.py
```
Veya projedeki `baslat.command` dosyasına çift tıklayarak çalıştırabilirsiniz.

---

## 📦 Paketleme / Building (.app)

Uygulamayı tek bir macOS paketi (.app) haline getirmek için:
```bash
pyinstaller GTranslate.spec
```
İşlem bittiğinde `dist/GTranslate.app` dosyası hazır olacaktır.

---

## 📋 Kullanım Klavuzu / Usage Guide

1.  **Pencere Seç:** Çevirmek istediğiniz uygulama penceresini listeden seçin.
2.  **Bölge Belirle:** "Bölge Seç" butonuna basarak ekranın hangi kısmının çevrileceğini fare ile işaretleyin.
3.  **Dili Ayarla:** Hedef dili seçin ve "Çeviriyi Başlat" butonuna basın.
4.  **İpucu:** Menü açıldığında başka bir yere tıklarsanız otomatik olarak menü barın içine gizlenir. Günlük panelini sabitlemek için panel üzerindeki "Sabitle" butonunu kullanabilirsiniz.

---

## 📄 Lisans / License
Bu proje MIT lisansı ile korunmaktadır.

---

*Geliştirici: [GitHub Kullanıcı Adınız]*
