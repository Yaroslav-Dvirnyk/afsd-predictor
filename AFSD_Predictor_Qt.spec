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
    # Что не нужно в Qt-сборке (иначе exe вырастает втрое):
    #   tkinter/PyQt* — вторая GUI-библиотека;
    #   scipy — тянется через matplotlib, но программа его не вызывает;
    #   Qt3D/Charts/WebEngine и прочее — модули Qt, которых нет в интерфейсе.
    excludes=[
        'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'scipy', 'pandas',
        'IPython', 'jupyter', 'notebook', 'pytest', 'PIL.ImageQt',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DExtras',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick', 'PySide6.QtQuick', 'PySide6.QtQml',
        'PySide6.QtQuick3D', 'PySide6.QtMultimedia', 'PySide6.QtBluetooth',
        'PySide6.QtNetworkAuth', 'PySide6.QtPositioning', 'PySide6.QtSensors',
        'PySide6.QtSerialPort', 'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtSpatialAudio',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
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
