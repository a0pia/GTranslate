# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GTranslate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file='entitlements.plist',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GTranslate',
)
app = BUNDLE(
    coll,
    name='GTranslate.app',
    icon='icon.icns',
    bundle_identifier='com.gtranslate.pro',
    info_plist={
        'NSHighResolutionCapable': True,
        'NSScreenCaptureUsageDescription': 'Uygulama ekranındaki metinleri okumak ve çevirmek için ekran kaydı iznine ihtiyaç duyar.',
        'NSAccessibilityUsageDescription': 'Uygulama pencereleri yönetmek ve odaklamak için erişilebilirlik iznine ihtiyaç duyar.',
        'LSUIElement': True, # Hide from Dock, keep in Menu Bar
        'NSRequiresAquaSystemAppearance': False,
    },
)
