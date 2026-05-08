# GTranslate - Real-time Screen Translation Tool (TR: Gerçek Zamanlı Ekran Çeviri Aracı)
import sys
import os
import threading
import hashlib
import re
import tempfile
import json

from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QLabel, QListWidget, QSlider, QHBoxLayout, QDialog,
    QRubberBand, QMessageBox, QSizePolicy, QComboBox, QInputDialog,
    QSystemTrayIcon, QMenu, QLineEdit, QStackedWidget
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QObject, QTimer, QPoint, QRect, QSize, 
    QPropertyAnimation, QEasingCurve, QEvent
)
from PyQt6.QtGui import QPixmap, QIcon, QAction, QCursor

from window_picker import (
    get_open_windows, capture_window, fast_capture_region, 
    check_and_request_permission
)
from ocr_engine import OCREngine
from translator import Translator
from translation_log import TranslationLogPanel

# --- Path handling for Bundled App ---
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

TEMP_DIR = tempfile.gettempdir()
WIN_CAPTURE_PATH = os.path.join(TEMP_DIR, "gtranslate_win.png")
REGION_TMP_PATH  = os.path.join(TEMP_DIR, "gtranslate_region.png")
CONFIG_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


# -- Signals ------------------------------------------------------------------
class WorkerSignals(QObject):
    # Signals to pass data from worker thread to UI thread
    translation_ready = pyqtSignal(object)  # (text, color)
    status_update     = pyqtSignal(str)
    start_timer       = pyqtSignal(int)
    stop_timer        = pyqtSignal()


# -- Screenshot-based Region Picker --------------------------------------------
class RegionPickerDialog(QDialog):
    """
    Captures a window screenshot, shows it in a dialog,
    and lets the user draw a rectangle to pick a sub-region.
    Returns region in SCREEN coordinates.
    """
    def __init__(self, window_info, parent=None):
        super().__init__(parent)
        self.window_info     = window_info
        self.selected_region = None
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self._origin  = QPoint()
        self._current = QPoint()
        self._drawing = False
        self._scale_x = 1.0
        self._scale_y = 1.0

        self.setWindowTitle("Bolge Sec - surukle ve birak -> onaylanir  |  ESC: iptal")
        self.setModal(True)
        self.setMinimumSize(400, 300)
        
        # Position at top-left of the screen
        self.move(20, 40) 

        self._img_label = QLabel(self)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setText("Ekran görüntüsü alınıyor…")
        self._img_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._img_label.setStyleSheet("background:#111; color:#aaa;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._img_label)

        hint = QLabel("Sol tus surukle -> bolge sec   |   ESC -> iptal")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color:#778; font-size:10px; padding:2px;")
        layout.addWidget(hint)

        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self._img_label)
        QTimer.singleShot(150, self._take_screenshot)

    def _take_screenshot(self):
        tmp = REGION_TMP_PATH
        img_path, _ = capture_window(self.window_info, tmp)
        if not img_path or not os.path.exists(img_path):
            QMessageBox.warning(self, "Hata", 
                                "Pencere ekran görüntüsü alınamadı.\n\n"
                                "Lütfen 'Sistem Ayarları > Gizlilik ve Güvenlik > Ekran Kaydı' "
                                "bölümünden Terminal veya Uygulama için izin verildiğinden emin olun.")
            self.reject()
            return

        px = QPixmap(img_path)
        if px.isNull():
            QMessageBox.warning(self, "Hata", "Ekran görüntüsü yüklenemedi.")
            self.reject()
            return

        screen  = QApplication.primaryScreen().geometry()
        max_w   = int(screen.width()  * 0.80)
        max_h   = int(screen.height() * 0.80)
        scaled  = px.scaled(max_w, max_h,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        self._img_label.setPixmap(scaled)
        self._img_label.setFixedSize(scaled.size())
        self.adjustSize()

        wx, wy, ww, wh = self.window_info['bounds']
        self._win_x   = wx
        self._win_y   = wy
        self._scale_x = ww / scaled.width()
        self._scale_y = wh / scaled.height()

        try:
            os.remove(img_path)
        except Exception:
            pass

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._img_label.pixmap():
            pos = self._img_label.mapFrom(self, e.pos())
            self._origin  = pos
            self._current = pos
            self._drawing = True
            self._rubber.setGeometry(QRect(pos, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, e):
        if self._drawing:
            pos = self._img_label.mapFrom(self, e.pos())
            self._current = pos
            self._rubber.setGeometry(QRect(self._origin, pos).normalized())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._drawing:
            self._drawing = False
            self._rubber.hide()
            rect = QRect(self._origin, self._current).normalized()
            if rect.width() < 10 or rect.height() < 10:
                return
            self.selected_region = {
                'rel_x':  int(rect.x() * self._scale_x),
                'rel_y':  int(rect.y() * self._scale_y),
                'width':  int(rect.width()  * self._scale_x),
                'height': int(rect.height() * self._scale_y),
            }
            self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.reject()


# -- Main control panel --------------------------------------------------------
class TranslatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GTranslate")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Popup |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setFixedWidth(265)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # --- Target Language Options (Localized) ---
        self.target_langs_data = [
            ("tr", {"tr": "Türkçe", "en": "Turkish", "de": "Türkisch", "fr": "Turc", "it": "Turco"}),
            ("en", {"tr": "İngilizce", "en": "English", "de": "Englisch", "fr": "Anglais", "it": "Inglese"}),
            ("de", {"tr": "Almanca", "en": "German", "de": "Deutsch", "fr": "Allemand", "it": "Tedesco"}),
            ("fr", {"tr": "Fransızca", "en": "French", "de": "Französisch", "fr": "Français", "it": "Francese"}),
            ("es", {"tr": "İspanyolca", "en": "Spanish", "de": "Spanisch", "fr": "Espagnol", "it": "Spagnolo"}),
            ("it", {"tr": "İtalyanca", "en": "Italian", "de": "Italienisch", "fr": "Italien", "it": "Italiano"}),
            ("ru", {"tr": "Rusça", "en": "Russian", "de": "Russisch", "fr": "Russe", "it": "Russo"}),
            ("ja", {"tr": "Japonca", "en": "Japanese", "de": "Japanisch", "fr": "Japonais", "it": "Giapponese"}),
            ("ko", {"tr": "Korece", "en": "Korean", "de": "Koreanisch", "fr": "Coréen", "it": "Coreano"}),
            ("zh-CN", {"tr": "Çince", "en": "Chinese", "de": "Chinesisch", "fr": "Chinois", "it": "Cinese"})
        ]
        
        self.i18n = {
            "tr": {
                "title": "GTranslate", "step1": "1. Pencere seç:", "step2": "2. Bölge seç:", "step3": "3. Hedef dil:",
                "desc_lang": "Çevirinin yapılmasını istediğiniz dili seçin.", "btn_start": "Çeviriyi Başlat",
                "btn_stop": "Durdur", "btn_log": "Günlük Panelini Aç/Kapat", "btn_hide": "Paneli Gizle",
                "btn_quit": "Tamamen Kapat", "status_ready": "Hazır.", "status_processing": "Çevriliyor...",
                "status_stopped": "Durduruldu.", "error_no_win": "HATA: Pencere seçilmedi!",
                "save_hint": "Bölge İsmi:", "save_confirm": "Kaydet ve Kapat", "ui_lang": "Dil:",
                "btn_clear_reg": "Bölgeyi Temizle", "scan_speed": "Tarama Hızı:", "delete": "Sil", "save": "S",
                "region_not_selected": "Bölge: Seçilmedi", "region_full": "Bölge: Tüm Pencere",
                "auto_selected": "Otomatik seçildi", "refresh": "Pencereleri Yenile", "pick_reg": "Pencereden Bölge Seç",
                "saved_regs_placeholder": "-- Kayıtlı Bölgeler --", "region_label": "Bölge",
                "pin": "Sabitle", "pinned": "Sabit"
            },
            "en": {
                "title": "GTranslate", "step1": "1. Select Window:", "step2": "2. Select Region:", "step3": "3. Target Language:",
                "desc_lang": "Choose the language you want to translate into.", "btn_start": "Start Translation",
                "btn_stop": "Stop", "btn_log": "Open/Close Log Panel", "btn_hide": "Hide Panel",
                "btn_quit": "Quit App", "status_ready": "Ready.", "status_processing": "Translating...",
                "status_stopped": "Stopped.", "error_no_win": "ERROR: No window selected!",
                "save_hint": "Region Name:", "save_confirm": "Save and Close", "ui_lang": "Language:",
                "btn_clear_reg": "Clear Region", "scan_speed": "Scan Speed:", "delete": "Del", "save": "S",
                "region_not_selected": "Region: Not Selected", "region_full": "Region: Full Window",
                "auto_selected": "Auto-selected", "refresh": "Refresh Windows", "pick_reg": "Pick Region",
                "saved_regs_placeholder": "-- Saved Regions --", "region_label": "Region",
                "pin": "Pin", "pinned": "Pinned"
            },
            "de": {
                "title": "GTranslate", "step1": "1. Fenster wählen:", "step2": "2. Bereich wählen:", "step3": "3. Zielsprache:",
                "desc_lang": "Wählen Sie die Sprache für die Übersetzung.", "btn_start": "Übersetzung starten",
                "btn_stop": "Stoppen", "btn_log": "Log-Panel öffnen/schließen", "btn_hide": "Panel ausblenden",
                "btn_quit": "Beenden", "status_ready": "Bereit.", "status_processing": "Übersetzen...",
                "status_stopped": "Gestoppt.", "error_no_win": "FEHLER: Kein Fenster gewählt!",
                "save_hint": "Bereichsname:", "save_confirm": "Speichern und Schließen", "ui_lang": "Sprache:",
                "btn_clear_reg": "Bereich löschen", "scan_speed": "Scan-Geschw.:", "delete": "Löschen", "save": "S",
                "region_not_selected": "Bereich: Nicht ausgewählt", "region_full": "Bereich: Ganzes Fenster",
                "auto_selected": "Automatisch ausgewählt", "refresh": "Fenster aktualisieren", "pick_reg": "Bereich wählen",
                "saved_regs_placeholder": "-- Gespeicherte Bereiche --", "region_label": "Bereich",
                "pin": "Fixieren", "pinned": "Fixiert"
            },
            "fr": {
                "title": "GTranslate", "step1": "1. Choisir la fenêtre:", "step2": "2. Choisir la région:", "step3": "3. Langue cible:",
                "desc_lang": "Choisissez la langue de traduction.", "btn_start": "Démarrer la traduction",
                "btn_stop": "Arrêter", "btn_log": "Ouvrir/Fermer le journal", "btn_hide": "Masquer le panneau",
                "btn_quit": "Quitter", "status_ready": "Prêt.", "status_processing": "Traduction...",
                "status_stopped": "Arrêté.", "error_no_win": "ERREUR: Aucune fenêtre sélectionnée!",
                "save_hint": "Nom de la région:", "save_confirm": "Enregistrer et Fermer", "ui_lang": "Langue:",
                "btn_clear_reg": "Effacer la région", "scan_speed": "Vitesse scan:", "delete": "Suppr", "save": "S",
                "region_not_selected": "Région: Non sélectionnée", "region_full": "Région: Fenêtre entière",
                "auto_selected": "Sélectionné automatiquement", "refresh": "Actualiser les fenêtres", "pick_reg": "Choisir la région",
                "saved_regs_placeholder": "-- Régions enregistrées --", "region_label": "Région",
                "pin": "Épingler", "pinned": "Épinglé"
            },
            "it": {
                "title": "GTranslate", "step1": "1. Scegli finestra:", "step2": "2. Scegli regione:", "step3": "3. Lingua target:",
                "desc_lang": "Scegli la lingua per la traduzione.", "btn_start": "Avvia traduzione",
                "btn_stop": "Ferma", "btn_log": "Apri/Chiudi log", "btn_hide": "Nascondi pannello",
                "btn_quit": "Esci", "status_ready": "Pronto.", "status_processing": "Traduzione...",
                "status_stopped": "Fermato.", "error_no_win": "ERRORE: Nessuna finestra scelta!",
                "save_hint": "Nome regione:", "save_confirm": "Salva e Chiudi", "ui_lang": "Lingua:",
                "btn_clear_reg": "Cancella regione", "scan_speed": "Velocità scan:", "delete": "Elimina", "save": "S",
                "region_not_selected": "Regione: Non selezionata", "region_full": "Regione: Intera finestra",
                "auto_selected": "Selezionato automaticamente", "refresh": "Aggiorna finestre", "pick_reg": "Scegli regione",
                "saved_regs_placeholder": "-- Regioni salvate --", "region_label": "Regione",
                "pin": "Fissa", "pinned": "Fissato",
                "perm_title": "Registrazione schermo richiesta",
                "perm_desc": "GTranslate ha bisogno del permesso 'Registrazione schermo' per acquisire e tradurre il testo da altre finestre.\n\n⚠️ Viene utilizzato solo per il riconoscimento del testo (OCR). I tuoi dati non vengono mai salvati o condivisi.",
                "perm_btn": "Apri Impostazioni di Sistema",
                "perm_footer": "Potrebbe essere necessario riavviare l'app dopo aver concesso il permesso."
            },
            "es": {
                "title": "GTranslate", "step1": "1. Seleccionar ventana:", "step2": "2. Seleccionar región:", "step3": "3. Idioma de destino:",
                "desc_lang": "Elija el idioma al que desea traducir.", "btn_start": "Iniciar traducción",
                "btn_stop": "Detener", "btn_log": "Abrir/Cerrar panel de registro", "btn_hide": "Ocultar panel",
                "btn_quit": "Salir", "status_ready": "Listo.", "status_processing": "Traduciendo...",
                "status_stopped": "Detenido.", "error_no_win": "ERROR: ¡No se seleccionó ninguna ventana!",
                "save_hint": "Nombre de la región:", "save_confirm": "Guardar y cerrar", "ui_lang": "Idioma:",
                "btn_clear_reg": "Borrar región", "scan_speed": "Velocidad de escaneo:", "delete": "Eliminar", "save": "G",
                "region_not_selected": "Región: No seleccionada", "region_full": "Región: Ventana completa",
                "auto_selected": "Seleccionado automáticamente", "refresh": "Actualizar ventanas", "pick_reg": "Elegir región",
                "saved_regs_placeholder": "-- Regiones guardadas --", "region_label": "Región",
                "pin": "Fijar", "pinned": "Fijado",
                "perm_title": "Se requiere grabación de pantalla",
                "perm_desc": "GTranslate necesita permiso de 'Grabación de pantalla' para capturar y traducir texto de otras ventanas.\n\n⚠️ Esto solo se usa para el reconocimiento de texto (OCR). Sus datos nunca se guardan ni se comparten.",
                "perm_btn": "Abrir configuración del sistema",
                "perm_footer": "Es posible que deba reiniciar la aplicación después de otorgar el permiso."
            },
            "ru": {
                "title": "GTranslate", "step1": "1. Выбрать окно:", "step2": "2. Выбрать область:", "step3": "3. Целевой язык:",
                "desc_lang": "Выберите язык для перевода.", "btn_start": "Начать перевод",
                "btn_stop": "Остановить", "btn_log": "Открыть/закрыть журнал", "btn_hide": "Скрыть панель",
                "btn_quit": "Выйти", "status_ready": "Готово.", "status_processing": "Перевод...",
                "status_stopped": "Остановлено.", "error_no_win": "ОШИБКА: Окно не выбрано!",
                "save_hint": "Имя области:", "save_confirm": "Сохранить и закрыть", "ui_lang": "Язык:",
                "btn_clear_reg": "Очистить область", "scan_speed": "Скорость сканирования:", "delete": "Удалить", "save": "С",
                "region_not_selected": "Область: Не выбрана", "region_full": "Область: Весь экран",
                "auto_selected": "Выбрано автоматически", "refresh": "Обновить окна", "pick_reg": "Выбрать область",
                "saved_regs_placeholder": "-- Сохраненные области --", "region_label": "Область",
                "pin": "Закрепить", "pinned": "Закреплено",
                "perm_title": "Требуется запись экрана",
                "perm_desc": "GTranslate требуется разрешение на «Запись экрана» для захвата и перевода текста из других окон.\n\n⚠️ Это используется только для распознавания текста (OCR). Ваши данные никогда не сохраняются и не передаются.",
                "perm_btn": "Открыть системные настройки",
                "perm_footer": "Возможно, вам потребуется перезапустить приложение после предоставления разрешения."
            },
            "ja": {
                "title": "GTranslate", "step1": "1. ウィンドウ選択:", "step2": "2. 範囲選択:", "step3": "3. 対象言語:",
                "desc_lang": "翻訳先の言語を選択してください。", "btn_start": "翻訳開始",
                "btn_stop": "停止", "btn_log": "ログパネル開閉", "btn_hide": "パネルを隠す",
                "btn_quit": "終了", "status_ready": "準備完了", "status_processing": "翻訳中...",
                "status_stopped": "停止中", "error_no_win": "エラー: ウィンドウが選択されていません",
                "save_hint": "範囲名:", "save_confirm": "保存して閉じる", "ui_lang": "言語:",
                "btn_clear_reg": "範囲をクリア", "scan_speed": "スキャンスピード:", "delete": "削除", "save": "保存",
                "region_not_selected": "範囲: 未選択", "region_full": "範囲: ウィンドウ全体",
                "auto_selected": "自動選択されました", "refresh": "ウィンドウ更新", "pick_reg": "範囲を指定",
                "saved_regs_placeholder": "-- 保存された範囲 --", "region_label": "範囲",
                "pin": "固定", "pinned": "固定済み",
                "perm_title": "画面収録の許可が必要です",
                "perm_desc": "GTranslateが他のウィンドウからテキストを読み取って翻訳するには、「画面収録」の許可が必要です。\n\n⚠️ これはテキスト認識（OCR）のみに使用されます。データが保存または共有されることはありません。",
                "perm_btn": "システム設定を開く",
                "perm_footer": "許可を与えた後、アプリの再起動が必要になる場合があります。"
            },
            "ko": {
                "title": "GTranslate", "step1": "1. 창 선택:", "step2": "2. 영역 선택:", "step3": "3. 대상 언어:",
                "desc_lang": "번역할 언어를 선택하세요.", "btn_start": "번역 시작",
                "btn_stop": "중지", "btn_log": "로그 패널 열기/닫기", "btn_hide": "패널 숨기기",
                "btn_quit": "종료", "status_ready": "준비됨", "status_processing": "번역 중...",
                "status_stopped": "중지됨", "error_no_win": "오류: 창이 선택되지 않았습니다!",
                "save_hint": "영역 이름:", "save_confirm": "저장 및 닫기", "ui_lang": "언어:",
                "btn_clear_reg": "영역 지우기", "scan_speed": "스캔 속도:", "delete": "삭제", "save": "저장",
                "region_not_selected": "영역: 선택되지 않음", "region_full": "영역: 전체 창",
                "auto_selected": "자동 선택됨", "refresh": "창 새로고침", "pick_reg": "영역 선택",
                "saved_regs_placeholder": "-- 저장된 영역 --", "region_label": "영역",
                "pin": "고정", "pinned": "고정됨",
                "perm_title": "화면 기록 권한 필요",
                "perm_desc": "GTranslate가 다른 창에서 텍스트를 캡처하고 번역하려면 '화면 기록' 권한이 필요합니다.\n\n⚠️ 이는 텍스트 인식(OCR)에만 사용됩니다. 데이터는 절대 저장되거나 공유되지 않습니다.",
                "perm_btn": "시스템 설정 열기",
                "perm_footer": "권한을 허용한 후 앱을 재시작해야 할 수도 있습니다."
            },
            "zh-CN": {
                "title": "GTranslate", "step1": "1. 选择窗口:", "step2": "2. 选择区域:", "step3": "3. 目标语言:",
                "desc_lang": "选择您想要翻译的目标语言。", "btn_start": "开始翻译",
                "btn_stop": "停止", "btn_log": "打开/关闭日志面板", "btn_hide": "隐藏面板",
                "btn_quit": "退出", "status_ready": "就绪", "status_processing": "正在翻译...",
                "status_stopped": "已停止", "error_no_win": "错误: 未选择窗口！",
                "save_hint": "区域名称:", "save_confirm": "保存并关闭", "ui_lang": "语言:",
                "btn_clear_reg": "清除区域", "scan_speed": "扫描速度:", "delete": "删除", "save": "保存",
                "region_not_selected": "区域: 未选择", "region_full": "区域: 整个窗口",
                "auto_selected": "自动选择", "refresh": "刷新窗口", "pick_reg": "选择区域",
                "saved_regs_placeholder": "-- 已保存区域 --", "region_label": "区域",
                "pin": "固定", "pinned": "已固定",
                "perm_title": "需要屏幕录制权限",
                "perm_desc": "GTranslate 需要“屏幕录制”权限才能从其他窗口抓取并翻译文本。\n\n⚠️ 这仅用于文本识别 (OCR)。您的数据绝不会被保存或共享。",
                "perm_btn": "打开系统设置",
                "perm_footer": "授予权限后，您可能需要重新启动应用程序。"
            }
        }
        self.current_ui_lang = "tr"
        
        self.setStyleSheet("""
            QWidget#MainContainer {
                background-color: rgba(0, 0, 0, 230);
                border: none;
                border-radius: 16px;
            }
            QWidget {
                color: #f0f0f0;
                font-family: '.AppleSystemUIFont', 'SF Pro Display', sans-serif;
            }
            QLabel#Title {
                color: #f1c40f;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 1px;
                margin-bottom: 2px;
            }
            QLabel#Step {
                color: #888;
                font-size: 10px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-top: 8px;
            }
            QLabel#Desc {
                color: #aaa;
                font-size: 9px;
                font-style: italic;
                margin-bottom: 2px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #ffffff;
                border: 1px solid rgba(241, 196, 15, 0.1);
                border-radius: 8px;
                padding: 7px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(241, 196, 15, 0.1);
                border-color: rgba(241, 196, 15, 0.3);
            }
            QPushButton#StartBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f1c40f, stop:1 #d4ac0d);
                color: #000000;
                border: none;
                font-weight: 800;
                font-size: 12px;
                padding: 12px;
                margin-top: 5px;
            }
            QPushButton#StartBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f4d03f, stop:1 #f1c40f);
            }
            QPushButton#StartBtn:checked {
                background: #e74c3c;
                color: #ffffff;
            }
            
            QListWidget {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(241, 196, 15, 0.1);
                border-radius: 8px;
                color: #eee;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: rgba(241, 196, 15, 0.2);
                color: #f1c40f;
                font-weight: bold;
            }
            
            QComboBox {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(241, 196, 15, 0.1);
                border-radius: 6px;
                color: #ffffff;
                padding: 6px 10px;
                font-size: 11px;
            }
            QComboBox QAbstractItemView {
                background: #111;
                border: 1px solid #f1c40f;
                color: #ffffff;
                selection-background-color: #f1c40f;
                selection-color: #000;
            }
            
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.05);
                height: 3px;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #f1c40f;
                width: 14px;
                height: 14px;
                margin: -6px 0;
                border-radius: 7px;
            }
        """)
        
        self.setWindowOpacity(0.98)

        self.ocr          = OCREngine()
        self.translator   = Translator(target_lang='tr')
        self.log_panel    = TranslationLogPanel()
        self.selected_window = None
        self.crop_region     = None
        self.is_processing   = False
        self.saved_regions   = {} # { window_name: { region_name: region_dict } }
        self._windows        = []
        self._speaker_shift_voter = 0
        self._candidate_color     = None
        self._last_img_hash  = ""
        self._last_ocr_text  = ""
        
        # --- Inline Save UI State ---
        self._save_ui_visible = False
        
        # --- Buffering for smooth sentences ---
        self._sentence_buffer = ""
        self._buffer_color    = None # color of current buffered speaker
        self._last_raw_text   = ""
        self._stability_count = 0
        
        self._buffer_timer    = QTimer()
        self._buffer_timer.setSingleShot(True)
        self._buffer_timer.timeout.connect(self._flush_buffer)
        self._buffer_lock     = threading.Lock()

        self.signals = WorkerSignals()
        self.signals.translation_ready.connect(self._on_translation)
        self.signals.status_update.connect(self.update_status)
        self.signals.start_timer.connect(self._buffer_timer.start)
        self.signals.stop_timer.connect(self._buffer_timer.stop)

        self._build_ui()
        self._level_set = False
        
        # Check macOS Screen Recording permissions on startup
        if not check_and_request_permission():
            self.update_status("Ekran Kaydi izni eksik!")
            QTimer.singleShot(1000, self._show_permission_warning)

        # --- Native macOS Popover Behavior ---
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            # Hide dock icon - makes it a true menu bar app
            NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception as e:
            print(f"Dock icon hide failed: {e}")

        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self.run_scan)

        # Initialize log panel position (but don't show yet)
        screen = QApplication.primaryScreen().geometry()
        self.log_panel.move(screen.width() - 420, screen.height() - 320)

        self._setup_tray()

    def _boost_level(self):
        """Force window to stay on top of other apps on macOS."""
        if self._level_set:
            return
        try:
            import objc
            from AppKit import NSStatusWindowLevel
            ns_view = objc.objc_object(c_void_p=int(self.winId()))
            ns_win  = ns_view.window()
            if ns_win:
                ns_win.setLevel_(NSStatusWindowLevel)
                ns_win.setCollectionBehavior_(1 << 2)  # CanJoinAllSpaces
                ns_win.setHidesOnDeactivate_(False)    # Keep visible when focus lost
            self._level_set = True
        except Exception as e:
            print(f"[main] level boost: {e}")

    def showEvent(self, e):
        super().showEvent(e)
        self._boost_level()

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create a very bold white 'G' for menu bar (ExtraBold weight)
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        from PyQt6.QtGui import QPainter, QColor, QFont
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a pure white "G" with maximum thickness
        painter.setPen(QColor(255, 255, 255))
        # ExtraBold weight (900) + Large font size + System Native
        font = QFont(".AppleSystemUIFont", 52, QFont.Weight.ExtraBold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "G")
        painter.end()
        
        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("GTranslate")
        
        # Tray Menu
        self.tray_menu = QMenu()
        
        # -- Permission Check Section --
        self.perm_action = QAction("⚠️ İzin Gerekiyor / Permission Required", self)
        self.perm_action.setVisible(False) # Default hidden
        self.perm_action.triggered.connect(self._open_system_settings)
        self.tray_menu.addAction(self.perm_action)
        self.tray_menu.addSeparator()
        
        # Check permissions after short delay to not block UI
        QTimer.singleShot(1000, self._check_and_update_permissions)
        
        quit_action = QAction("Tamamen Kapat / Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        self.tray_menu.addAction(quit_action)
        
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _check_and_update_permissions(self):
        """Checks macOS permissions and updates the menu."""
        import Quartz
        import ApplicationServices
        
        # 1. Screen Recording Check
        # Robust check: try a dummy 1x1 capture
        has_screen = Quartz.CGPreflightScreenCaptureAccess()
        
        # 2. Accessibility Check
        has_acc = ApplicationServices.AXIsProcessTrusted()
        
        # Update UI Labels
        t = self.i18n[self.current_ui_lang]
        scr_text = "🎥 Ekran Kaydı / Screen Recording: "
        acc_text = "🖱 Erişilebilirlik / Accessibility: "
        
        if has_screen:
            self.status_screen.setText(f"{scr_text} ✅")
            self.status_screen.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.status_screen.setText(f"{scr_text} ❌")
            self.status_screen.setStyleSheet("color: #e74c3c; font-weight: bold;")

        if has_acc:
            self.status_acc.setText(f"{acc_text} ✅")
            self.status_acc.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.status_acc.setText(f"{acc_text} ❌")
            self.status_acc.setStyleSheet("color: #e74c3c; font-weight: bold;")
            
        if has_screen and has_acc:
            self.perm_action.setVisible(False)
            self.stack.setCurrentIndex(0) # Show normal UI
        else:
            self.perm_action.setVisible(True)
            self.perm_action.setText("⚠️ " + t.get("perm_title", "Permission Required"))
            self.stack.setCurrentIndex(1) # Show permission page

    def _open_system_settings(self):
        """Opens macOS System Settings for Privacy & Security."""
        import subprocess
        # Opens the Privacy & Security panel directly
        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"])
        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])

        # Animation setup
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(200)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visibility()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self.tray_menu.exec(QCursor.pos())

    def toggle_visibility(self, force_show=False):
        if self.isVisible() and not force_show:
            self.hide()
        else:
            self.show()

    def show(self):
        """Show window with fade-in and slide-down animation from tray icon."""
        # Refresh permission status every time we show
        self._check_and_update_permissions()
        
        # Position window under tray icon
        tray_rect = self.tray_icon.geometry()
        screen = QApplication.primaryScreen().availableGeometry()
        
        if tray_rect.isNull() or tray_rect.x() == 0:
            x = screen.right() - self.width() - 20
            y = screen.top() + 5
        else:
            pos = tray_rect.bottomLeft()
            x = pos.x() - self.width() // 2 + tray_rect.width() // 2
            y = pos.y() + 2
        
        # Clamp to screen
        x = max(screen.left() + 10, min(x, screen.right() - self.width() - 10))
        
        start_pos = QPoint(x, y - 15)
        end_pos   = QPoint(x, y)
        
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        super().show()
        self.raise_()
        self.activateWindow()
        
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(250)
        self._anim.setStartValue(start_pos)
        self._anim.setEndValue(end_pos)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(250)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        
        self._anim.start()
        self._fade_anim.start()
        self._boost_level()

    def hide(self):
        """Hide window with fade-out and slide-up animation."""
        if not self.isVisible() or hasattr(self, '_hiding'):
            return
            
        self._hiding = True
        self._hide_anim = QPropertyAnimation(self, b"windowOpacity")
        self._hide_anim.setDuration(200)
        self._hide_anim.setStartValue(self.windowOpacity())
        self._hide_anim.setEndValue(0.0)
        self._hide_anim.finished.connect(self._finish_hide)
        
        self._hide_pos = QPropertyAnimation(self, b"pos")
        self._hide_pos.setDuration(200)
        self._hide_pos.setStartValue(self.pos())
        self._hide_pos.setEndValue(QPoint(self.x(), self.y() - 15))
        
        self._hide_anim.start()
        self._hide_pos.start()

    def _finish_hide(self):
        super().hide()
        self.setWindowOpacity(1.0)
        if hasattr(self, '_hiding'):
            del self._hiding

    # -- UI --------------------------------------------------------------------
    def _build_ui(self):
        # Create a container widget for the styling to apply correctly with translucency
        self.main_container = QWidget(self)
        self.main_container.setObjectName("MainContainer")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_container)

        self.stack = QStackedWidget(self.main_container)
        container_lay = QVBoxLayout(self.main_container)
        container_lay.setContentsMargins(0, 0, 0, 0)
        container_lay.addWidget(self.stack)

        # --- PAGE 1: NORMAL UI ---
        self.page_ui = QWidget()
        lay = QVBoxLayout(self.page_ui)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(8)
        self.stack.addWidget(self.page_ui)

        # --- PAGE 2: PERMISSION OVERLAY ---
        self.page_perm = QWidget()
        perm_lay = QVBoxLayout(self.page_perm)
        perm_lay.setContentsMargins(15, 15, 15, 15)
        perm_lay.setSpacing(12)

        # Header controls for permission page
        perm_header = QHBoxLayout()
        self.lbl_ui_lang_perm = QLabel("Dil:")
        self.lbl_ui_lang_perm.setStyleSheet("font-size: 9px; color: #777;")
        perm_header.addWidget(self.lbl_ui_lang_perm)
        
        self.combo_ui_lang_perm = QComboBox()
        self.combo_ui_lang_perm.addItems(["Türkçe", "English", "Deutsch", "Français", "Italiano"])
        self.combo_ui_lang_perm.setFixedWidth(80)
        self.combo_ui_lang_perm.setStyleSheet("font-size: 9px; height: 18px; padding: 0 4px;")
        self.combo_ui_lang_perm.currentTextChanged.connect(self._on_ui_lang_changed)
        perm_header.addWidget(self.combo_ui_lang_perm)
        perm_header.addStretch()
        perm_lay.addLayout(perm_header)
        
        icon_lbl = QLabel("⚠️")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 32px; margin-top: 5px;")
        perm_lay.addWidget(icon_lbl)
        
        self.perm_title_lbl = QLabel("Permission Required")
        self.perm_title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.perm_title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #f1c40f;")
        perm_lay.addWidget(self.perm_title_lbl)
        
        self.perm_desc_lbl = QLabel("...")
        self.perm_desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.perm_desc_lbl.setWordWrap(True)
        self.perm_desc_lbl.setStyleSheet("font-size: 10px; color: #ccc; line-height: 1.3;")
        perm_lay.addWidget(self.perm_desc_lbl)

        # Status Indicators
        status_box = QWidget()
        status_box.setStyleSheet("background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px;")
        status_lay = QVBoxLayout(status_box)
        
        self.status_screen = QLabel("🎥 Ekran Kaydı / Screen Recording: ⏳")
        self.status_acc = QLabel("🖱 Erişilebilirlik / Accessibility: ⏳")
        status_lay.addWidget(self.status_screen)
        status_lay.addWidget(self.status_acc)
        perm_lay.addWidget(status_box)
        
        self.btn_open_perms = QPushButton("Open System Settings")
        self.btn_open_perms.setObjectName("StartBtn")
        self.btn_open_perms.clicked.connect(self._open_system_settings)
        perm_lay.addWidget(self.btn_open_perms)

        self.btn_refresh_perms = QPushButton("🔄 İzinleri Kontrol Et / Check Permissions")
        self.btn_refresh_perms.setStyleSheet("background: rgba(255,255,255,0.05); font-size: 10px;")
        self.btn_refresh_perms.clicked.connect(self._check_and_update_permissions)
        perm_lay.addWidget(self.btn_refresh_perms)
        
        perm_lay.addStretch()

        self.perm_footer_lbl = QLabel("...")
        self.perm_footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.perm_footer_lbl.setStyleSheet("font-size: 9px; color: #666; font-style: italic;")
        perm_lay.addWidget(self.perm_footer_lbl)
        
        self.btn_quit_perm = QPushButton("Quit App")
        self.btn_quit_perm.setStyleSheet("background: rgba(231, 76, 60, 0.15); color: #ff7675; font-size:11px;")
        self.btn_quit_perm.clicked.connect(QApplication.instance().quit)
        perm_lay.addWidget(self.btn_quit_perm)
        
        self.stack.addWidget(self.page_perm)

        # -- UI Language Selector (Added at the very top) --
        ui_lang_lay = QHBoxLayout()
        self.lbl_ui_lang = QLabel("Dil:")
        self.lbl_ui_lang.setStyleSheet("font-size: 9px; color: #777;")
        ui_lang_lay.addWidget(self.lbl_ui_lang)
        
        self.combo_ui_lang = QComboBox()
        self.combo_ui_lang.addItems(["Türkçe", "English", "Deutsch", "Français", "Italiano"])
        self.combo_ui_lang.setFixedWidth(80)
        self.combo_ui_lang.setStyleSheet("font-size: 9px; height: 18px; padding: 0 4px;")
        self.combo_ui_lang.currentTextChanged.connect(self._on_ui_lang_changed)
        ui_lang_lay.addWidget(self.combo_ui_lang)
        ui_lang_lay.addStretch()
        lay.addLayout(ui_lang_lay)

        self.title_lbl = QLabel("GTranslate")
        self.title_lbl.setObjectName("Title")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.title_lbl)

        # -- Step 1: -----------------------------------------------------------
        self.lbl_step1 = self._step("1. Pencere seç:")
        lay.addWidget(self.lbl_step1)
        self.window_list = QListWidget()
        self.window_list.setMaximumHeight(120)
        self.window_list.itemClicked.connect(self._on_window_clicked)
        lay.addWidget(self.window_list)

        self.btn_refresh = QPushButton("Pencereleri Yenile")
        self.btn_refresh.clicked.connect(self.refresh_windows)
        lay.addWidget(self.btn_refresh)

        # -- Step 2: -----------------------------------------------------------
        self.lbl_step2 = self._step("2. Bölge seç:")
        lay.addWidget(self.lbl_step2)
        self.btn_region = QPushButton("Pencereden Bölge Seç")
        self.btn_region.clicked.connect(self.select_region)
        lay.addWidget(self.btn_region)

        self.region_lbl = QLabel("Bölge: Seçilmedi")
        self.region_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.region_lbl)

        row_reg = QHBoxLayout()
        self.combo_regions = QComboBox()
        self.combo_regions.currentTextChanged.connect(self._on_region_combo_changed)
        row_reg.addWidget(self.combo_regions, 1)

        self.btn_save_reg = QPushButton("S")
        self.btn_save_reg.setFixedWidth(30)
        self.btn_save_reg.clicked.connect(self.save_current_region)
        row_reg.addWidget(self.btn_save_reg)
        
        self.btn_del_reg = QPushButton("Sil")
        self.btn_del_reg.setFixedWidth(30)
        self.btn_del_reg.setStyleSheet("background: rgba(231, 76, 60, 0.1); color: #ff7675;")
        self.btn_del_reg.clicked.connect(self.delete_current_region)
        row_reg.addWidget(self.btn_del_reg)
        
        lay.addLayout(row_reg)

        # -- Inline Save Input (Animated) --------------------------------------
        self.save_widget = QWidget()
        self.save_widget.setMaximumHeight(0)
        self.save_widget.setContentsMargins(0, 0, 0, 0)
        self.save_widget.setStyleSheet("background: rgba(46, 204, 113, 0.05); border-radius: 8px;")
        
        save_lay = QVBoxLayout(self.save_widget)
        save_lay.setContentsMargins(8, 8, 8, 8)
        save_lay.setSpacing(6)
        
        self.save_hint_lbl = QLabel("Bölge İsmi:")
        self.save_hint_lbl.setStyleSheet("color: #f1c40f; font-weight: bold; font-size: 10px;")
        save_lay.addWidget(self.save_hint_lbl)
        
        self.save_input = QLineEdit()
        self.save_input.setPlaceholderText("...")
        self.save_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(241, 196, 15, 0.2);
                border-radius: 5px; color: #fff; padding: 5px; font-size: 11px;
            }
        """)
        self.save_input.returnPressed.connect(self._do_inline_save)
        save_lay.addWidget(self.save_input)
        
        self.btn_confirm_save = QPushButton("Kaydet ve Kapat")
        self.btn_confirm_save.setStyleSheet("background: #d4ac0d; color: #000; font-weight: bold; height: 24px;")
        self.btn_confirm_save.clicked.connect(self._do_inline_save)
        save_lay.addWidget(self.btn_confirm_save)
        
        lay.addWidget(self.save_widget)
        
        # Animation for save widget
        self._save_anim = QPropertyAnimation(self.save_widget, b"maximumHeight")
        self._save_anim.setDuration(250)
        self._save_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.btn_clear_region = QPushButton("Bölgeyi Temizle")
        self.btn_clear_region.clicked.connect(self.clear_region)
        lay.addWidget(self.btn_clear_region)

        # -- Status bar ------------------------------------------------------
        row = QHBoxLayout()
        self.lbl_speed_text = QLabel("Tarama Hızı:")
        row.addWidget(self.lbl_speed_text)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(300)
        self.speed_slider.setMaximum(5000)
        self.speed_slider.setValue(800)
        row.addWidget(self.speed_slider)
        self.speed_lbl = QLabel("0.6s")
        self.speed_lbl.setFixedWidth(32)
        row.addWidget(self.speed_lbl)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        lay.addLayout(row)

        # -- Step 3: Hedef Dil -------------------------------------------------
        self.lbl_step3 = self._step("3. Hedef dil:")
        lay.addWidget(self.lbl_step3)
        self.desc_lang_lbl = QLabel("...")
        self.desc_lang_lbl.setObjectName("Desc")
        lay.addWidget(self.desc_lang_lbl)
        
        self.combo_lang = QComboBox()
        self.combo_lang.currentTextChanged.connect(self._on_language_changed)
        lay.addWidget(self.combo_lang)

        # -- Start / Stop ------------------------------------------------------
        self.btn_start = QPushButton("...")
        self.btn_start.setObjectName("StartBtn")
        self.btn_start.setCheckable(True)
        self.btn_start.clicked.connect(self.toggle)
        lay.addWidget(self.btn_start)
        
        self.btn_log = QPushButton("...")
        self.btn_log.setStyleSheet("font-size: 9px; padding: 4px; color: #778;")
        self.btn_log.clicked.connect(self._toggle_log)
        lay.addWidget(self.btn_log)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status_lbl)

        lay.addSpacing(5)
        
        # -- Footer Actions ----------------------------------------------------
        footer_lay = QHBoxLayout()
        
        self.btn_hide = QPushButton("...")
        self.btn_hide.setStyleSheet("background: rgba(255,255,255,0.08); color:#aaa; font-size:11px;")
        self.btn_hide.clicked.connect(self.hide)
        footer_lay.addWidget(self.btn_hide)
        
        self.btn_quit = QPushButton("...")
        self.btn_quit.setStyleSheet("background: rgba(231, 76, 60, 0.15); color: #ff7675; font-size:11px;")
        self.btn_quit.clicked.connect(QApplication.instance().quit)
        footer_lay.addWidget(self.btn_quit)
        
        lay.addLayout(footer_lay)

        self.retranslate_ui()
        self.refresh_windows()
        self.load_config()

    def save_config(self):
        config = {
            'last_window_name': self.selected_window['name'] if self.selected_window else None,
            'crop_region': self.crop_region,
            'saved_regions': self.saved_regions,
            'target_lang': self.combo_lang.currentText() if hasattr(self, 'combo_lang') else "Türkçe",
            'ui_lang': self.current_ui_lang
        }
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Config save error: {e}")

    def load_config(self):
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return
                config = json.loads(content)
                self.saved_regions = config.get('saved_regions', {})
                last_win = config.get('last_window_name')
                saved_region = config.get('crop_region')
                target_lang = config.get('target_lang', "Türkçe")
                self.current_ui_lang = config.get('ui_lang', "tr")
                
                if hasattr(self, 'combo_ui_lang'):
                    self.combo_ui_lang.blockSignals(True)
                    self.combo_ui_lang_perm.blockSignals(True)
                    rev_mapping = {"tr": "Türkçe", "en": "English", "de": "Deutsch", "fr": "Français", "it": "Italiano"}
                    text = rev_mapping.get(self.current_ui_lang, "English")
                    self.combo_ui_lang.setCurrentText(text)
                    self.combo_ui_lang_perm.setCurrentText(text)
                    self.combo_ui_lang.blockSignals(False)
                    self.combo_ui_lang_perm.blockSignals(False)
                    self.retranslate_ui()
                
                if hasattr(self, 'combo_lang'):
                    self.combo_lang.setCurrentText(target_lang)
                
                if last_win:
                    for i in range(self.window_list.count()):
                        item = self.window_list.item(i)
                        if last_win in item.text():
                            self.window_list.setCurrentRow(i)
                            idx = self.window_list.row(item)
                            self.selected_window = self._windows[idx]
                            self.update_status(f"Otomatik seçildi: {self.selected_window['name']}")
                            self._update_region_combo()
                            break
                
                if saved_region:
                    self.crop_region = saved_region
                    self.region_lbl.setText(
                        f"Bölge: {saved_region['width']}×{saved_region['height']} (Kayıtlı)"
                    )
                    self.region_lbl.setStyleSheet("color:#2ecc71; font-size:10px;")
                    self._reset_cache()
        except Exception as e:
            print(f"Config load error: {e}")

    def _on_language_changed(self, _):
        idx = self.combo_lang.currentIndex()
        lang_code = self.combo_lang.itemData(idx) if idx >= 0 else "tr"
        lang_name = self.combo_lang.currentText()
        
        self.translator.change_target_language(lang_code)
        self.update_status(f"OK: {lang_name}")
        self.save_config()

    def _update_region_combo(self):
        self.combo_regions.blockSignals(True)
        self.combo_regions.clear()
        self.combo_regions.addItem("-- Kayıtlı Bölgeler --")
        if self.selected_window:
            win_name = self.selected_window['name']
            regions = self.saved_regions.get(win_name, {})
            for name in regions.keys():
                self.combo_regions.addItem(name)
        self.combo_regions.blockSignals(False)

    def save_current_region(self):
        if not self.selected_window or not self.crop_region:
            self.update_status("HATA: Pencere/Bölge seçilmedi!")
            self.status_lbl.setStyleSheet("color: #ff7675; font-size: 10px; font-weight: bold;")
            QTimer.singleShot(2000, lambda: self.status_lbl.setStyleSheet("color: #888; font-size: 10px;"))
            return
            
        if self._save_ui_visible:
            self._collapse_save_ui()
        else:
            self._expand_save_ui()

    def _expand_save_ui(self):
        self._save_ui_visible = True
        self._save_anim.setStartValue(0)
        self._save_anim.setEndValue(90)
        self._save_anim.start()
        self.save_input.setFocus()

    def _collapse_save_ui(self):
        self._save_ui_visible = False
        self._save_anim.setStartValue(90)
        self._save_anim.setEndValue(0)
        self._save_anim.start()
        self.save_input.clear()

    def _do_inline_save(self):
        name = self.save_input.text().strip()
        if name:
            win_name = self.selected_window['name']
            if win_name not in self.saved_regions:
                self.saved_regions[win_name] = {}
            self.saved_regions[win_name][name] = self.crop_region
            self._update_region_combo()
            self.combo_regions.setCurrentText(name)
            self.save_config()
            self.update_status(f"Kaydedildi: {name}")
            self._collapse_save_ui()
        else:
            self.update_status("İsim girilmedi!")

    def delete_current_region(self):
        name = self.combo_regions.currentText()
        if not self.selected_window or name == "-- Kayıtlı Bölgeler --" or not name:
            return
            
        win_name = self.selected_window['name']
        if win_name in self.saved_regions and name in self.saved_regions[win_name]:
            del self.saved_regions[win_name][name]
            self._update_region_combo()
            self.save_config()
            self.update_status(f"Silindi: {name}")
            self.crop_region = None
            self.region_lbl.setText("Bölge: Seçilmedi")
            self.region_lbl.setStyleSheet("color: #888;")

    def _on_region_combo_changed(self, name):
        if not self.selected_window or name == "-- Kayıtlı Bölgeler --" or not name:
            return
            
        win_name = self.selected_window['name']
        region = self.saved_regions.get(win_name, {}).get(name)
        if region:
            self.crop_region = region
            self.region_lbl.setText(
                f"Bölge: {region['width']}×{region['height']} ({name})"
            )
            self.region_lbl.setStyleSheet("color:#f1c40f; font-size:10px;")
            self._reset_cache()
            self.save_config()

    def _show_permission_warning(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("İzin Gerekli")
        msg.setText("Uygulamanın çalışması için 'Ekran Kaydı' izni gerekiyor.")
        msg.setInformativeText(
            "Lütfen Sistem Ayarları'nı açın ve bu uygulamaya (veya Terminal'e) izin verin.\n\n"
            "İzin verdikten sonra uygulamayı yeniden başlatmanız gerekebilir."
        )
        btn_settings = msg.addButton("Ayarları Aç", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Tamam", QMessageBox.ButtonRole.AcceptRole)
        
        msg.exec()
        
        if msg.clickedButton() == btn_settings:
            import subprocess
            subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"])

    def retranslate_ui(self):
        t = self.i18n[self.current_ui_lang]
        self.lbl_ui_lang.setText(t["ui_lang"])
        self.title_lbl.setText(t["title"])
        self.lbl_step1.setText(t["step1"])
        self.btn_refresh.setText(t["refresh"])
        self.lbl_step2.setText(t["step2"])
        self.btn_region.setText(t["pick_reg"])
        self.btn_save_reg.setToolTip(t["save"])
        self.btn_del_reg.setToolTip(t["delete"])
        self.btn_del_reg.setText(t["delete"])
        self.save_hint_lbl.setText(t["save_hint"])
        self.btn_confirm_save.setText(t["save_confirm"])
        self.btn_clear_region.setText(t["btn_clear_reg"])
        self.lbl_step3.setText(t["step3"])
        self.desc_lang_lbl.setText(t["desc_lang"])
        self.btn_log.setText(t["btn_log"])
        self.btn_hide.setText(t["btn_hide"])
        self.btn_quit.setText(t["btn_quit"])
        
        # Permission Page (With safety checks)
        self.perm_title_lbl.setText(t.get("perm_title", "Permission Required"))
        self.perm_desc_lbl.setText(t.get("perm_desc", "This app needs screen recording permission to function."))
        self.btn_open_perms.setText(t.get("perm_btn", "Open System Settings"))
        self.perm_footer_lbl.setText(t.get("perm_footer", ""))
        self.btn_quit_perm.setText(t["btn_quit"])
        self.lbl_ui_lang_perm.setText(t["ui_lang"])
        self.lbl_speed_text.setText(t["scan_speed"])
        
        # Sync Log Panel Language
        if hasattr(self, 'log_panel'):
            self.log_panel.retranslate_ui(self.current_ui_lang)
        
        # Localize Region Label
        if not self.crop_region:
            self.region_lbl.setText(t["region_not_selected"])
        else:
            self.region_lbl.setText(f"{t['region_label']}: {self.crop_region['width']}×{self.crop_region['height']}")

        # Localize combo_regions placeholder
        self.combo_regions.blockSignals(True)
        if self.combo_regions.count() > 0 and self.combo_regions.itemText(0).startswith("--"):
            self.combo_regions.setItemText(0, t["saved_regs_placeholder"])
        self.combo_regions.blockSignals(False)

        # Localize combo_lang items
        current_target_code = self._get_current_target_code()
        self.combo_lang.blockSignals(True)
        self.combo_lang.clear()
        for code, names in self.target_langs_data:
            localized_name = names.get(self.current_ui_lang, names["en"])
            self.combo_lang.addItem(localized_name, code)
            if code == current_target_code:
                self.combo_lang.setCurrentText(localized_name)
        self.combo_lang.blockSignals(False)

        # Update dynamic start/stop button
        if self.btn_start.isChecked():
            self.btn_start.setText(t["btn_stop"])
        else:
            self.btn_start.setText(t["btn_start"])
            
        # Update status if ready or auto-selected
        curr_status = self.status_lbl.text()
        if curr_status in ["Hazır.", "Ready.", "Bereit.", "Prêt.", "Pronto."]:
            self.status_lbl.setText(t["status_ready"])
        elif "Otomatik seçildi" in curr_status or "Auto-selected" in curr_status or "Automatisch" in curr_status:
            # Re-construct auto-selected message
            win_name = curr_status.split(":")[-1].strip()
            self.status_lbl.setText(f"{t['auto_selected']}: {win_name}")

    def _get_current_target_code(self):
        """Helper to get current target lang code from combo regardless of UI lang."""
        idx = self.combo_lang.currentIndex()
        if idx >= 0:
            return self.combo_lang.itemData(idx)
        return "tr"

    def _on_ui_lang_changed(self, text):
        mapping = {
            "Türkçe": "tr", "English": "en", "Deutsch": "de", 
            "Français": "fr", "Italiano": "it"
        }
        self.current_ui_lang = mapping.get(text, "en")
        self.retranslate_ui()
        self.save_config()

    def _step(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Step")
        return lbl

    def _on_speed_changed(self, v):
        self.speed_lbl.setText(f"{v/1000:.1f}s")
        if self.scan_timer.isActive():
            self.scan_timer.setInterval(v)

    def _toggle_log(self):
        if self.log_panel.isVisible():
            self.log_panel.hide()
        else:
            self.log_panel.show()
            self.log_panel.raise_()
            self.log_panel._boost_level() # Re-ensure PiP level

    # -- Window / Region -------------------------------------------------------
    def refresh_windows(self):
        self.window_list.clear()
        self._windows = get_open_windows()
        for w in self._windows:
            self.window_list.addItem(f"{w['display']}")
        self.retranslate_ui()

    def _on_window_clicked(self, item):
        idx = self.window_list.row(item)
        if 0 <= idx < len(self._windows):
            self.clear_region()
            self.selected_window = self._windows[idx]
            self.update_status(f"Seçildi: {self._windows[idx]['name']}")
            self._update_region_combo()
            self.save_config()

    def _get_selected_window(self):
        idx = self.window_list.currentRow()
        if 0 <= idx < len(self._windows):
            return self._windows[idx]
        return None

    def select_region(self):
        win = self._get_selected_window()
        if not win:
            self.update_status("Hata: Önce listeden bir pencere seçin!")
            self.tray_icon.showMessage(
                "GTranslate", 
                "Lütfen önce bir pencere seçin!",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
            self.toggle_visibility(force_show=True)
            return
        self.update_status("Ekran görüntüsü alınıyor…")
        QApplication.processEvents()
        dlg = RegionPickerDialog(win, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_region:
            region = dlg.selected_region
            self.crop_region = region
            self.region_lbl.setText(
                f"Bölge: {region['width']}×{region['height']} "
                f" (Pencere içi: {region['rel_x']},{region['rel_y']})"
            )
            self.region_lbl.setStyleSheet("color:#2ecc71; font-size:10px;")
            self._reset_cache()
            self.update_status("Bolge secildi")
            self.save_config()
        else:
            self.update_status("İptal edildi.")

    def clear_region(self):
        self.crop_region = None
        self.region_lbl.setText("Bölge: Tüm Pencere")
        self.region_lbl.setStyleSheet("color:#778; font-size:10px;")
        self._reset_cache()
        self.save_config()

    def _reset_cache(self):
        self._last_img_hash = ""
        self._last_ocr_text = ""
        self._last_raw_text = ""
        self._stability_count = 0
        self._speaker_shift_voter = 0
        self._candidate_color = None
        with self._buffer_lock:
            self._sentence_buffer = ""
            self._buffer_color    = None
        self.signals.stop_timer.emit()

    # -- Translation loop ------------------------------------------------------
    def toggle(self):
        if self.btn_start.isChecked():
            win = self._get_selected_window()
            if not win:
                self.update_status("Pencere seçin!")
                self.btn_start.setChecked(False)
                return
            
            # Auto-open log panel if it's hidden when starting translation
            if not self.log_panel.isVisible():
                self._toggle_log()

            self.selected_window = win
            self._reset_cache()
            self.btn_start.setText("Durdur")
            self.scan_timer.start(self.speed_slider.value())
            self.log_panel.update_title(win['name'])
            self.update_status(f"Çevriliyor: {win['name']}")
        else:
            self.btn_start.setText("Ceviriyi Baslat")
            self.scan_timer.stop()
            self._buffer_timer.stop()
            self.is_processing = False
            self.update_status("Durduruldu.")

    def run_scan(self):
        if self.is_processing:
            return
        self.is_processing = True
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        try:
            # -- 1. Capture (Window-locked) ------------------------------------
            # Re-fetch window bounds to track movement
            cur_win = None
            for w in get_open_windows():
                if w['id'] == self.selected_window['id']:
                    cur_win = w
                    break
            
            if not cur_win:
                self.signals.status_update.emit("Pencere bulunamadı.")
                return

            # Capture the specific window (even if obscured)
            img_path, _ = capture_window(cur_win, WIN_CAPTURE_PATH)
            
            if not img_path or not os.path.exists(img_path):
                self.signals.status_update.emit("Yakalama başarısız.")
                return

            # If a sub-region is selected, crop it from the window capture
            if self.crop_region:
                try:
                    from PIL import Image
                    full_img = Image.open(img_path)
                    
                    # Calculate scale (OCR logical vs pixel)
                    # screencapture -l usually gives pixels
                    lw = cur_win['bounds'][2]
                    scale = full_img.width / lw if lw > 0 else 1.0
                    
                    rx = int(self.crop_region['rel_x'] * scale)
                    ry = int(self.crop_region['rel_y'] * scale)
                    rw = int(self.crop_region['width'] * scale)
                    rh = int(self.crop_region['height'] * scale)
                    
                    # Clamp to window image
                    rx = max(0, min(rx, full_img.width - 1))
                    ry = max(0, min(ry, full_img.height - 1))
                    rw = min(rw, full_img.width - rx)
                    rh = min(rh, full_img.height - ry)
                    
                    if rw > 5 and rh > 5:
                        cropped = full_img.crop((rx, ry, rx + rw, ry + rh))
                        cropped_path = WIN_CAPTURE_PATH + "_cropped.png"
                        cropped.save(cropped_path)
                        img_path = cropped_path
                except Exception as e:
                    print(f"Crop error: {e}")

            # -- 2. Image hash - skip if screen unchanged -----------------------
            img_hash = _file_hash(img_path)
            if img_hash == self._last_img_hash:
                return   # nothing changed on screen
            self._last_img_hash = img_hash
            
            # -- 3. OCR + Processing -------------------------------------------
            blocks = self.ocr.recognize_text_with_bounds(img_path)
            if not blocks:
                # If screen went blank, flush buffer immediately
                if self._sentence_buffer:
                    self._flush_buffer()
                return

            good_blocks = []
            for b in blocks:
                line_score, _ = _coherence_score(b['text'])
                if line_score >= 0.15:
                    good_blocks.append(b)

            if not good_blocks:
                # If no meaningful text, wait (timer handles flush)
                return

            # Combine blocks and get raw color
            combined, text_color = _blocks_to_text(good_blocks)
            
            # Clean text: remove bullet points, stray symbols, weird OCR noise
            combined = re.sub(r'^[•\-\*,\'\"\.\:\;\!\?\s]+', '', combined)
            combined = re.sub(r'\s+', ' ', combined).strip()
            
            if not combined or len(combined) < 2:
                return

            raw_norm = combined.lower().strip()

            # -- 4. Color Smoothing and Speaker Change Logic -----------------
            def get_saturation(c):
                if not c: return 0
                try:
                    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
                    mx, mn = max(r,g,b), min(r,g,b)
                    return (mx - mn) / mx if mx > 0 else 0
                except: return 0

            def get_color_quality(c):
                if not c: return 0
                try:
                    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
                    mx = max(r, g, b)
                    sat = (mx - min(r, g, b)) / mx if mx > 0 else 0
                    val = mx / 255.0
                    return sat * 0.8 + val * 0.2 
                except: return 0

            # Determine "Resolved" color
            current_sat = get_saturation(text_color)
            resolved_color = text_color if text_color else "#ffffff"
            
            # Color similarity with tolerance
            def colors_similar(c1, c2):
                if not c1 or not c2: return False
                if c1 == c2: return True
                try:
                    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
                    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
                    dist = abs(r1-r2) + abs(g1-g2) + abs(b1-b2)
                    
                    if dist < 120: return True 
                    
                    s1, s2 = get_saturation(c1), get_saturation(c2)
                    if s1 > 0.12 and s2 > 0.12:
                        def fast_hue(r, g, b):
                            mx, mn = max(r,g,b), min(r,g,b)
                            if mx == mn: return 0
                            d = mx - mn
                            if mx == r: h = (g - b) / d + (6 if g < b else 0)
                            elif mx == g: h = (b - r) / d + 2
                            else: h = (r - g) / d + 4
                            return h * 60
                        
                        h1 = fast_hue(r1, g1, b1)
                        h2 = fast_hue(r2, g2, b2)
                        h_diff = abs(h1 - h2)
                        if h_diff > 180: h_diff = 360 - h_diff
                        
                        if h_diff < 45 and dist < 320:
                            return True
                            
                    return False
                except: return False

            flush_text = None
            flush_color = None

            with self._buffer_lock:
                # If current frame has no color but we are already tracking a speaker,
                # assume it's the same person (persistence).
                if text_color is None and self._buffer_color:
                    resolved_color = self._buffer_color

                # High Persistence: If the current color is in the same "family" 
                # as the buffered color, keep the buffered color.
                if self._buffer_color and colors_similar(resolved_color, self._buffer_color):
                    # Upgrade to better (more vibrant) version if available
                    if get_color_quality(resolved_color) > get_color_quality(self._buffer_color):
                        self._buffer_color = resolved_color
                    resolved_color = self._buffer_color
                elif self._buffer_color and current_sat < 0.20:
                    if get_saturation(self._buffer_color) > 0.35:
                        resolved_color = self._buffer_color

                # Speaker Shift Trigger (Hysteresis / Voter System)
                # We require multiple frames of the SAME new color to trigger a shift.
                is_similar = colors_similar(resolved_color, self._buffer_color)
                if self._buffer_color and not is_similar:
                    if self._candidate_color and colors_similar(resolved_color, self._candidate_color):
                        self._speaker_shift_voter += 1
                    else:
                        self._candidate_color = resolved_color
                        self._speaker_shift_voter = 1
                    
                    if self._speaker_shift_voter >= 3: # Confirmed shift (after ~2.5 seconds)
                        if self._sentence_buffer:
                            flush_text = self._sentence_buffer
                            flush_color = self._buffer_color
                        
                        self._sentence_buffer = combined
                        self._buffer_color = resolved_color
                        self._speaker_shift_voter = 0
                        self._candidate_color = None
                        self._stability_count = 0
                        self._last_raw_text = raw_norm
                    else:
                        # Unconfirmed shift: Stay with current speaker for now
                        resolved_color = self._buffer_color
                else:
                    # Color is similar or no buffer, reset voter
                    self._speaker_shift_voter = 0
                    self._candidate_color = None
                    
                    if not self._buffer_color:
                        self._buffer_color = resolved_color

                    if raw_norm == self._last_raw_text:
                        self._stability_count += 1
                    else:
                        self._sentence_buffer = combined
                        self._last_raw_text = raw_norm
                        self._stability_count = 0
                
                # Safety Flush (Stability)
                # If speaker hasn't changed but text is stable for ~3 seconds
                if self._stability_count >= 5 and self._sentence_buffer:
                    flush_text = self._sentence_buffer
                    flush_color = self._buffer_color
                    self._sentence_buffer = ""
                    self._stability_count = 0

            # -- 5. Translation Block (OUTSIDE lock) ------------------------
            if flush_text:
                score, _ = _coherence_score(flush_text)
                if score > 0.12:
                    self.signals.stop_timer.emit()
                    self._do_translate(flush_text, score, flush_color)
            
            if not flush_text:
                self.signals.status_update.emit(f"Diyalog biriktiriliyor ({resolved_color})")
                self.signals.start_timer.emit(5000)

        except Exception as e:
            self.signals.status_update.emit(f"Hata: {e}")
        finally:
            self.is_processing = False

    def _flush_buffer(self):
        """Timer callback: translate whatever is in the buffer."""
        with self._buffer_lock:
            if not self._sentence_buffer:
                return
            text_to_translate = self._sentence_buffer
            self._sentence_buffer = ""
        
        # Score it again to be safe
        score, _ = _coherence_score(text_to_translate)
        self._do_translate(text_to_translate, score, None)

    def _do_translate(self, text: str, score: float, color: str = None):
        """Helper to perform the actual translation call."""
        try:
            translated = self.translator.translate(text)
            if translated and translated.strip():
                self.signals.translation_ready.emit((translated.strip(), color))
                self.signals.status_update.emit(f"Tamamlandi ({score:.0%})")
        except Exception as e:
            self.signals.status_update.emit(f"Hata: {e}")

    def _on_translation(self, data):
        text, color = data if isinstance(data, tuple) else (data, None)
        self.log_panel.add_translation(text, color)

    def update_status(self, text: str):
        self.status_lbl.setText(text)


# -- Helpers -------------------------------------------------------------------

# Common English words for coherence detection (~350 most frequent)
_ENGLISH_WORDS = frozenset({
    'a','an','the','and','or','but','if','in','on','at','to','for','of',
    'with','by','from','is','are','was','were','be','been','being',
    'have','has','had','do','does','did','will','would','could','should',
    'may','might','shall','can','not','no','yes','it','its','he','she',
    'we','they','you','me','him','her','us','them','my','your','his',
    'our','their','this','that','these','those','what','which','who',
    'how','when','where','why','all','any','some','more','most','other',
    'also','just','here','there','now','then','so','too','very','well',
    'back','even','still','only','up','out','about','into','through',
    'before','after','over','under','again','own','same','much','many',
    'long','little','first','last','right','left','next','new','old',
    'big','small','good','great','high','low','open','close','hard',
    'easy','free','real','man','men','woman','women','boy','girl',
    'child','people','world','life','time','day','night','year','week',
    'place','way','thing','work','hand','eye','head','door','home',
    'name','word','line','side','end','part','point','face','room',
    'game','road','city','body','move','turn','help','need','look',
    'come','take','make','know','go','get','see','say','think','find',
    'use','feel','try','ask','tell','call','keep','give','hold','put',
    'let','run','stop','start','show','play','wait','walk','stand',
    'fall','leave','lose','win','break','carry','reach','bring','send',
    'jump','fight','sit','stay','save','follow','return','watch','hear',
    'read','write','live','die','eat','sleep','talk','speak','meet',
    'remember','never','always','every','each','both','between','while',
    'though','because','since','until','unless','without','within',
    'around','along','across','behind','below','above','near','far',
    'away','together','already','soon','later','once','twice','else',
    'sure','okay','ok','please','sorry','thank','thanks',
    'hey','hi','hello','oh','ah',
    'im','ive','ill','id','youre','hes','shes','theyre','were','dont',
    'doesnt','didnt','wont','wouldnt','couldnt','shouldnt','cant',
    'isnt','arent','wasnt','werent','hasnt','havent','thats','whats',
    'heres','theres','its','lets','weve','theyll','shell','hell',
    # -- Game / menu vocabulary --
    'continue','quit','resume','options','settings','menu','pause',
    'level','exit','select','checkpoint','controls','control','audio',
    'video','volume','screen','display','language','difficulty',
    'mission','player','health','weapon','ammo','item','inventory',
    'map','camera','vibration','brightness','contrast','music','sound',
    'effects','subtitles','captions','loading','load','save','delete',
    'new','create','profile','slot','confirm','cancel','back','apply',
    'reset','default','on','off','enabled','disabled','auto','manual',
    'low','medium','high','ultra','custom','play','playing','played',
    'buy','purchase','upgrade','equip','use','equipped','locked',
    'unlocked','complete','completed','failed','retry','restart',
    'skip','unskippable','tutorial','hint','tip','objective','goal',
    'score','points','coins','money','currency','lives','life',
    'shield','armor','attack','defend','dodge','dash','sprint','walk',
    'climb','swim','fly','shoot','fire','reload','aim','throw','grab',
    'push','pull','open','close','interact','action','press','hold',
})


def _coherence_score(text: str) -> tuple[float, list[str]]:
    """
    Returns (score, known_words).
    score  : 0.0-1.0 - how likely the OCR text is real English.
    known_words: English words found (for partial-mode translation).

    Scoring:
      85% weight -> ratio of words that appear in _ENGLISH_WORDS
      15% weight -> ratio of words with good alphabetic quality
    """
    raw = re.findall(r"[a-zA-Z']+", text)
    if not raw:
        return 0.0, []

    alpha_words = []
    known: list[str] = []

    for w in raw:
        w_clean = re.sub(r"'", '', w).lower()
        if len(w_clean) < 2:
            continue
        alpha_words.append(w_clean)
        if w_clean in _ENGLISH_WORDS:
            known.append(w)          # keep original casing for translation

    if not alpha_words:
        return 0.0, []

    common_ratio  = len(known) / len(alpha_words)
    quality_words = sum(1 for w in alpha_words if 3 <= len(w) <= 16)
    quality_ratio = quality_words / len(alpha_words)

    base = common_ratio * 0.80 + quality_ratio * 0.10

    # Punctuation bonus - real sentences tend to have punctuation
    if re.search(r'[.!?]', text):               # sentence-ending -> strong signal
        punct_bonus = 0.20
    elif re.search(r"[,;:'\"\(\)\-]", text):    # other punctuation -> moderate signal
        punct_bonus = 0.10
    else:
        punct_bonus = 0.0

    score = min(1.0, base + punct_bonus)
    return score, known

def _jaccard_sim(a: str, b: str) -> float:
    """
    Jaccard similarity on word sets.
    Returns 0.0-1.0; higher = more similar.
    E.g. 'run along ropes jump' vs 'run ropes jump' -> ~0.75
    """
    if not a or not b:
        return 0.0
    wa = set(a.split())
    wb = set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _normalize_text(text: str) -> str:
    """
    Normalizes text for deduplication:
    - lowercase
    - collapse punctuation/special chars
    - collapse whitespace
    So 'Hello world.' and 'Hello world' hash to the same string.
    """
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)   # remove punctuation
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _file_hash(path: str) -> str:
    """MD5 of first 64 KB - fast enough to detect any screen change."""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read(65536))
    return h.hexdigest()


def _blocks_to_text(blocks: list[dict]) -> tuple[str, str | None]:
    """
    Converts OCR blocks to a single string preserving reading order.
    Returns (combined_text, dominant_color).
    """
    if not blocks:
        return "", None
    # Sort top-to-bottom, left-to-right
    sorted_blocks = sorted(blocks, key=lambda b: (round(b['norm_y'] / 0.05), b['norm_x']))
    lines   = []
    prev_y  = None
    cur_line = []
    
    # Track the color of the first block (usually character name or primary text)
    primary_color = sorted_blocks[0].get('color')
    
    for b in sorted_blocks:
        cy = b['norm_y']
        if prev_y is None or abs(cy - prev_y) < 0.04:
            cur_line.append(b['text'])
        else:
            lines.append(' '.join(cur_line))
            cur_line = [b['text']]
        prev_y = cy
    if cur_line:
        lines.append(' '.join(cur_line))
    return '\n'.join(lines), primary_color


# -- Entry point ---------------------------------------------------------------
if __name__ == "__main__":
    # Singleton check using a lock file
    import tempfile
    lock_path = os.path.join(tempfile.gettempdir(), "gtranslate.lock")
    
    # Try to open/create lock file
    try:
        if os.path.exists(lock_path):
            # Check if process is still alive (crude check)
            try:
                os.remove(lock_path)
            except:
                # On macOS, if the file is locked, this will fail
                pass
        
        lock_file = open(lock_path, "w")
        import fcntl
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            print("Uygulama zaten calisiyor!")
            sys.exit(0)
            
        lock_file.write(str(os.getpid()))
        lock_file.flush()
    except Exception as e:
        print(f"Lock error: {e}")

    app = QApplication(sys.argv)
    app.setApplicationName("GTranslate")
    app.setQuitOnLastWindowClosed(False) # Don't quit when window is hidden
    
    win = TranslatorApp()
    
    print("\n" + "="*40)
    print(" GTranslate Başlatıldı!")
    print(" Menü barındaki beyaz 'G' ikonuna tıklayın.")
    print("="*40 + "\n")
    
    sys.exit(app.exec())
