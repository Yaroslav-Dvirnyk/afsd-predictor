# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['afsd_predictor.py'],
    pathex=[],
    binaries=[],
    datas=[('user_materials.json', '.'), ('user_mu.json', '.'), ('app.ico', '.')],
    # Ядро расчёта и отрисовка графика — обычные импорты, но перечислены
    # явно, чтобы анализатор их точно не пропустил.
    hiddenimports=['afsd_core', 'afsd_plot'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt в этой сборке не нужен (интерфейс на tkinter), а scipy/pandas
    # тянутся через matplotlib, хотя программа их не вызывает. Без этих
    # исключений однофайловый exe разрастается и дольше распаковывается.
    excludes=[
        'PySide6', 'PyQt5', 'PyQt6', 'PySide2', 'shiboken6',
        'scipy', 'pandas', 'IPython', 'jupyter', 'notebook', 'pytest',
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
    name='AFSD_Predictor',
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
