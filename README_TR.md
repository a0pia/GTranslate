# GTranslate - Gerçek Zamanlı Ekran Çeviri Aracı 🌍

**GTranslate**, macOS işletim sistemi için geliştirilmiş, ekran üzerindeki metinleri (oyunlar, videolar, dokümanlar) gerçek zamanlı olarak yakalayıp istediğiniz dile çeviren modern ve şık bir araçtır.

[English Version (İngilizce Versiyon)](README.md)

---

## 🚀 Özellikler

- **Apple Vision OCR:** macOS'in yerleşik yapay zekasını kullanarak yüksek doğrulukta metin tanıma.
- **Gerçek Zamanlı Çeviri:** Google Translate (deep-translator) altyapısı ile anlık çeviri.
- **Modern Arayüz:** "Midnight Gold" temalı, macOS yerel uygulaması hissi veren tasarım.
- **Akıllı Gizleme (Auto-Hide):** Menü çubuğu odağı kaybettiğinde otomatik olarak gizlenir.
- **Çeviri Günlüğü (Log Panel):** Geçmiş çevirileri renk kodları ve konuşmacı ayrımı ile takip edin.
- **Sabitleme (Pin):** Günlük panelini ekranın istediğiniz yerinde her zaman üstte tutun.

---

## 🛠 Kurulum ve Hazırlık

### 1. Projeyi İndirin
Terminali açın ve şu komutları sırasıyla çalıştırın:
```bash
git clone https://github.com/a0pia/GTranslate.git
cd GTranslate
```

### 2. Gereksinimler
- macOS (Apple Vision API desteği için gereklidir)
- Python 3.9+

### 3. Kütüphaneleri Yükleyin
```bash
pip install -r requirements.txt
```

---

## 🏃 Uygulamayı Çalıştırma

Uygulamayı başlatmak için:
```bash
python3 main.py
```
Alternatif olarak, proje klasöründeki `baslat.command` dosyasına çift tıklayarak da çalıştırabilirsiniz.

---

## 📦 Paketleme (.app Yapma)

Uygulamayı tek başına çalışan bir macOS paketi (.app) haline getirmek için:
```bash
pyinstaller GTranslate.spec
```
İşlem tamamlandığında `dist/GTranslate.app` klasörü altında uygulamanız hazır olacaktır.

---

## 📋 Kullanım Kılavuzu

1.  **Pencere Seç:** Çevirmek istediğiniz uygulama penceresini listeden seçin.
2.  **Bölge Belirle:** "Bölge Seç" butonuna basın ve ekranın çevrilmesini istediğiniz alanını fare ile kare içine alın.
3.  **Başlat:** Hedef dili seçin ve "Çeviriyi Başlat" butonuna basın.
4.  **İpucu:** Menü açıldığında başka bir yere tıklarsanız otomatik olarak gizlenir. Günlük panelini ekranda sabit tutmak için paneldeki "Sabitle" butonunu kullanabilirsiniz.

---

## 📄 Lisans
Bu proje **MIT Lisansı** ile korunmaktadır.

**MIT Lisansı Nedir?**
- **Özgürlük:** Kodu istediğiniz gibi kullanabilir, kopyalayabilir, değiştirebilir ve satabilirsiniz.
- **Sorumluluk:** Yazılım "olduğu gibi" sunulur; herhangi bir garanti verilmez.
- **Koşul:** Lisans dosyasını ve telif hakkı bildirimini korumanız yeterlidir.

---

*Geliştirici: [a0pia](https://github.com/a0pia)*
