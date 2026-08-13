# -*- coding: utf-8 -*-
"""
AFSD Predictor — тема оформления Qt-интерфейса.

Единая палитра токенов вместо цветов, разбросанных по коду: у каждого
цвета одна роль (фон, поверхность, текст, акцент, граница), и обе темы —
светлая и тёмная — задают один и тот же набор ролей. Виджеты ссылаются
на роль, а не на конкретный #rrggbb, поэтому переключение темы меняет
только эту таблицу.

Палитра графика (matplotlib) выводится из тех же токенов, чтобы карта
и 3D-поверхность не выглядели вставкой из другой программы.
"""

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Palette:
    """Роли цветов. Одинаковый набор в светлой и тёмной теме."""
    name: str
    bg: str            # фон окна
    surface: str       # панели, карточки
    surface_alt: str   # чередование строк, вложенные блоки
    border: str        # границы и разделители
    text: str          # основной текст
    text_dim: str      # подписи, единицы измерения, подсказки
    accent: str        # акцент: активные вкладки, фокус, главная кнопка
    accent_hover: str
    accent_text: str   # текст на акценте
    ok: str            # «в окне» — результат в допуске
    warn: str          # предупреждение (близко к солидусу)
    danger: str        # выход за окно / ошибка
    plot_bg: str       # фон полотна графика
    plot_axes: str     # фон области осей
    grid: str          # сетка графика


LIGHT = Palette(
    name="light",
    bg="#f4f6fa",
    surface="#ffffff",
    surface_alt="#eef2f8",
    border="#d3dae6",
    text="#1a2130",
    text_dim="#5f6b80",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_text="#ffffff",
    ok="#137a3a",
    warn="#b25e00",
    danger="#c02434",
    plot_bg="#ffffff",
    plot_axes="#ffffff",
    grid="#dde3ec",
)

DARK = Palette(
    name="dark",
    bg="#151922",
    surface="#1c2230",
    surface_alt="#232b3b",
    border="#333d51",
    text="#e6ebf4",
    text_dim="#9aa7bd",
    accent="#5b8cff",
    accent_hover="#7aa2ff",
    accent_text="#0f1420",
    ok="#3ecf72",
    warn="#e8a33d",
    danger="#ff6b7a",
    plot_bg="#1c2230",
    plot_axes="#1c2230",
    grid="#333d51",
)

THEMES = {"light": LIGHT, "dark": DARK}

# Шкала отступов: один шаг = 4 px. Вёрстка использует только эти значения,
# поэтому расстояния в интерфейсе согласованы между панелями.
SP_XS, SP_S, SP_M, SP_L, SP_XL = 2, 4, 8, 12, 16
RADIUS = 6


def qss(p: Palette, base_pt: int = 10, family: str = "Segoe UI") -> str:
    """Таблица стилей Qt для палитры p."""
    d = asdict(p)
    # Высоты элементов считаются от кегля: 1 pt ≈ 1.333 px, плюс место под
    # выносные элементы букв и рамку. Иначе при смене размера шрифта текст
    # начинает подрезаться снизу.
    px = base_pt * 4.0 / 3.0
    d.update(radius=RADIUS, sp_s=SP_S, sp_m=SP_M, sp_l=SP_L,
             family=family, base_pt=base_pt, small_pt=max(7, base_pt - 1),
             ctl_h=int(px + 10), btn_h=int(px + 12))
    return """
* {{ font-family: "{family}"; font-size: {base_pt}pt; }}

QWidget {{ background: {bg}; color: {text}; }}

QToolTip {{
    background: {surface}; color: {text};
    border: 1px solid {border}; border-radius: {radius}px; padding: {sp_s}px;
}}

/* ---- панели-карточки ---- */
QFrame#Card {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {radius}px;
}}
QLabel#CardTitle {{
    color: {text}; font-weight: 600; font-size: {base_pt}pt;
    background: transparent; padding: 0;
}}
QLabel#Hint, QLabel#Unit {{ color: {text_dim}; font-size: {small_pt}pt; background: transparent; }}
QLabel {{ background: transparent; }}

/* ---- поля ввода ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: {sp_s}px {sp_m}px;
    /* min-height обязателен: Qt не добавляет padding из QSS к расчётной
       высоте виджета, и без него текст с выносными элементами подрезается */
    min-height: {ctl_h}px;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {text_dim}; background: {surface_alt};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {surface}; color: {text};
    border: 1px solid {border};
    selection-background-color: {accent}; selection-color: {accent_text};
    outline: none;
}}

/* ---- кнопки ---- */
QPushButton {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: {sp_m}px {sp_l}px;
    min-height: {btn_h}px;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:pressed {{ background: {surface_alt}; }}
QPushButton:disabled {{ color: {text_dim}; border-color: {border}; }}
QPushButton#Accent {{
    background: {accent}; color: {accent_text};
    border: 1px solid {accent}; font-weight: 600;
}}
QPushButton#Accent:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton:checked {{ background: {accent}; color: {accent_text}; border-color: {accent}; }}

/* ---- вкладки ---- */
QTabWidget::pane {{
    border: 1px solid {border}; border-radius: {radius}px;
    background: {surface}; top: -1px;
}}
QTabBar::tab {{
    background: transparent; color: {text_dim};
    padding: {sp_m}px {sp_l}px; margin-right: {sp_s}px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
QTabBar::tab:hover:!selected {{ color: {text}; }}

/* ---- таблицы ---- */
QHeaderView::section {{
    background: {surface_alt}; color: {text_dim};
    border: none; border-bottom: 1px solid {border};
    padding: {sp_m}px; font-weight: 600;
}}
QTableView, QTreeView, QListWidget {{
    background: {surface}; alternate-background-color: {surface_alt};
    border: 1px solid {border}; border-radius: {radius}px;
    gridline-color: {border};
    selection-background-color: {accent}; selection-color: {accent_text};
    outline: none;
}}

/* ---- полосы прокрутки: тонкие, без стрелок ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {border}; border-radius: 5px; min-height: 28px; min-width: 28px;
}}
QScrollBar::handle:hover {{ background: {text_dim}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- прочее ---- */
QSplitter::handle {{ background: {border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QMenuBar, QMenu {{ background: {surface}; color: {text}; border: none; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
QMenu {{ border: 1px solid {border}; border-radius: {radius}px; padding: {sp_s}px; }}
QMenu::item {{ padding: {sp_s}px {sp_l}px; border-radius: {radius}px; }}
QMenu::separator {{ height: 1px; background: {border}; margin: {sp_s}px {sp_m}px; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: {sp_m}px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QGroupBox {{
    border: 1px solid {border}; border-radius: {radius}px;
    margin-top: {sp_l}px; padding-top: {sp_l}px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: {sp_m}px; color: {text_dim}; }}
QStatusBar {{ background: {surface}; border-top: 1px solid {border}; color: {text_dim}; }}
QSlider::groove:horizontal {{ height: 4px; background: {border}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {accent}; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px;
}}
""".format(**d)


def mpl_rc(p: Palette, family: str = "DejaVu Sans", size: int = 11) -> dict:
    """Настройки matplotlib в тон интерфейсу.

    Возвращает словарь для rcParams. Экспорт в статью делается отдельно на
    белом фоне — тёмная тема нужна на экране, а не в PDF для журнала.
    """
    return {
        "figure.facecolor": p.plot_bg,
        "axes.facecolor": p.plot_axes,
        "savefig.facecolor": p.plot_bg,
        "text.color": p.text,
        "axes.labelcolor": p.text,
        "axes.edgecolor": p.border,
        "xtick.color": p.text_dim,
        "ytick.color": p.text_dim,
        "grid.color": p.grid,
        "font.family": family,
        "font.size": size,
        "axes.titlesize": size + 1,
        "axes.grid": True,
        "grid.alpha": 0.45,
        "grid.linewidth": 0.6,
        "figure.autolayout": False,
        "legend.facecolor": p.surface,
        "legend.edgecolor": p.border,
        "legend.labelcolor": p.text,
    }
