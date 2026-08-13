# -*- mode: python ; coding: utf-8 -*-
# Сборка Qt-версии. Ядро расчёта (afsd_core) и тема (afsd_theme) указаны
# явно: главный модуль тянет их обычным импортом, но hiddenimports страхует
# от того, что анализатор их пропустит.

a = Analysis(
    ['afsd_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('user_materials.json', '.'), ('user_mu.json', '.'), ('app.ico', '.')],
    hiddenimports=['afsd_core', 'afsd_theme'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Что не нужно в Qt-сборке (иначе exe вырастает вдвое):
    #   tkinter/PyQt* — вторая GUI-библиотека;
    #   scipy/pandas — тянутся через matplotlib, но программа их не вызывает.
    # Отдельные модули PySide6 здесь НЕ исключаются: Qt подгружает часть из
    # них динамически (QtSvg нужен для иконок панели инструментов), и обрезка
    # по именам давала exe, который запускался, но не показывал окно.
    excludes=[
        'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'scipy', 'pandas',
        'IPython', 'jupyter', 'notebook', 'pytest',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AFSD_Predictor_Qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)

# Сборка папкой, а не одним файлом: однофайловый exe распаковывает ~80 МБ во
# временный каталог при каждом запуске, что на этой машине блокируется и окно
# не появляется. Папка стартует сразу и без распаковки.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AFSD_Predictor_Qt',
)
