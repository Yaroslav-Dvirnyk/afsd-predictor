# -*- coding: utf-8 -*-
"""
AFSD Predictor — интерфейс на PySide6.

Расчёты берутся из afsd_core.ModelState — того же кода, что и у прежнего
Tk-окна, поэтому оба интерфейса считают одинаково. Оформление — из
afsd_theme. Здесь только представление: ни одной формулы.

Запуск:  python afsd_qt.py
"""

import os
import sys
import json
import math

import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QActionGroup, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox, QTabWidget,
    QSplitter, QFrame, QScrollArea, QSizePolicy, QStatusBar, QMessageBox,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QRadioButton,
    QButtonGroup, QSlider, QDoubleSpinBox, QSpinBox, QTextEdit, QDialog,
    QDialogButtonBox, QAbstractItemView, QToolButton,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

import afsd_core as core
from afsd_theme import THEMES, qss, mpl_rc, SP_S, SP_M, SP_L, SP_XL


# ---------------------------------------------------------------------------
#  строительные блоки
# ---------------------------------------------------------------------------
class Card(QFrame):
    """Панель-карточка с заголовком и вертикальной раскладкой внутри."""

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SP_L, SP_L, SP_L, SP_L)
        outer.setSpacing(SP_M)
        self._title = None
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("CardTitle")
            outer.addWidget(lbl)
            self._title = lbl
        self.body = QVBoxLayout()
        self.body.setSpacing(SP_M)
        outer.addLayout(self.body)
        # карточка занимает ровно столько, сколько нужно содержимому, и не
        # растягивается: иначе последняя строка обрезается или карточки
        # наезжают друг на друга
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def set_title(self, text):
        if self._title:
            self._title.setText(text)


class Field(QWidget):
    """Подпись + поле ввода + единица измерения — одной строкой."""

    def __init__(self, label, value="", unit="", width=92, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        # вертикальные поля строки — иначе соседние строки наезжают друг на
        # друга: QLineEdit со своей высотой выше интервала по умолчанию
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(SP_M)
        self.label = QLabel(label)
        self.edit = QLineEdit(str(value))
        self.edit.setFixedWidth(width)
        self.edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.unit = QLabel(unit)
        self.unit.setObjectName("Unit")
        self.unit.setMinimumWidth(46)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.edit, 0)
        lay.addWidget(self.unit, 0)
        # Высота задаётся явно, а не через QSS: min-height из таблицы стилей
        # не попадает в sizeHint(), поэтому layout выделяет строке слишком
        # мало места и последняя в карточке подрезается.
        h = self.fontMetrics().height() + 14
        self.edit.setMinimumHeight(h)
        self.setMinimumHeight(h + 4)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def text(self):
        return self.edit.text()

    def value(self, default=0.0):
        try:
            return float(self.edit.text().strip().replace(",", "."))
        except ValueError:
            return default

    def set_value(self, v):
        self.edit.setText(("%g" % v) if isinstance(v, (int, float)) else str(v))

    def set_label(self, text):
        self.label.setText(text)


class RangeRow(QWidget):
    """Строка параметра режима: [диапазон/фикс] min…max либо одно значение.

    Переключатель слева решает, входит ли параметр в матрицу планирования и
    может ли стать осью карты, — это и есть смысл «range» в модели.
    """

    def __init__(self, sym, disp, unit, parent=None):
        super().__init__(parent)
        self.sym = sym
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(SP_S)

        self.chk = QCheckBox(disp)
        self.chk.setMinimumWidth(58)
        self.chk.setToolTip("Варьировать: параметр входит в план 3ᴺ и может быть осью карты")
        self.e_min = QLineEdit(); self.e_max = QLineEdit(); self.e_pt = QLineEdit()
        for e in (self.e_min, self.e_max, self.e_pt):
            e.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            e.setFixedWidth(66)
            e.setMinimumHeight(self.fontMetrics().height() + 14)
        self.lbl_dots = QLabel("…")
        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setObjectName("Unit")
        self.lbl_unit.setMinimumWidth(52)

        lay.addWidget(self.chk, 0)
        lay.addWidget(self.e_min, 0)
        lay.addWidget(self.lbl_dots, 0)
        lay.addWidget(self.e_max, 0)
        lay.addWidget(self.e_pt, 0)
        lay.addWidget(self.lbl_unit, 0)
        lay.addStretch(1)
        self.setMinimumHeight(self.fontMetrics().height() + 18)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set_range_mode(self, on):
        """В режиме «фикс» диапазон не участвует в расчёте — гасим поля."""
        self.e_min.setEnabled(on)
        self.e_max.setEnabled(on)
        self.lbl_dots.setEnabled(on)


class PlotPane(QWidget):
    """Полотно matplotlib с панелью навигации."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.fig = Figure(figsize=(7.2, 5.4), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas, 1)

    def style_axes(self, pal):
        """Перекрасить оси под тему (вызывать после отрисовки)."""
        self.fig.set_facecolor(pal.plot_bg)
        for ax in self.fig.get_axes():
            ax.set_facecolor(pal.plot_axes)
            for spine in ax.spines.values():
                spine.set_edgecolor(pal.border)
            ax.tick_params(colors=pal.text_dim)
            ax.xaxis.label.set_color(pal.text)
            ax.yaxis.label.set_color(pal.text)
            ax.title.set_color(pal.text)
            if hasattr(ax, "zaxis"):        # 3D: своя ось и панели
                try:
                    ax.zaxis.label.set_color(pal.text)
                    ax.tick_params(axis="z", colors=pal.text_dim)
                    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
                        pane.set_facecolor(pal.plot_axes)
                        pane.set_edgecolor(pal.border)
                except Exception:
                    pass
        self.canvas.draw_idle()


# ---------------------------------------------------------------------------
#  главное окно
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.st = core.ModelState()
        self.lang = "en"
        self.theme_name = "dark"
        self.view = "2D"
        self._project_path = None
        self._last_grid = None
        self._points = []             # нанесённые точки: [{label, vals, T}]
        self._building = False        # защита от рекурсии при обновлении полей
        # реестры для смены языка на лету: (виджет, ключ перевода, запасной текст)
        self._titled_cards = []
        self._texted = []
        self._labeled_fields = []

        self.setWindowTitle(core.APP_NAME)
        self.resize(1560, 960)
        self.setMinimumSize(1200, 780)
        try:
            self.setWindowIcon(QIcon(core._bundled_file("app.ico")))
        except Exception:
            pass

        self._build_menu()
        self._build_ui()
        self.setStatusBar(QStatusBar())
        self.apply_theme(self.theme_name)
        self._state_to_widgets()
        QTimer.singleShot(60, self.rebuild)
        QTimer.singleShot(200, self._mark_saved)

    # ---------- перевод ----------
    def t(self, key, fallback=None):
        if self.lang == "zh" and key in core.ZH:
            return core.ZH[key]
        d = core.TR.get(key)
        if not d:
            return fallback or key
        return d.get(self.lang) or d.get("en") or fallback or key

    # ---------- меню ----------
    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu(self.t("menu_file", "Файл"))
        for key, fb, slot, seq in [
            ("menu_new", "Новый", self.on_new, QKeySequence.New),
            ("menu_open", "Открыть…", self.on_open, QKeySequence.Open),
            ("menu_save", "Сохранить", self.on_save, QKeySequence.Save),
            ("menu_saveas", "Сохранить как…", self.on_save_as, QKeySequence.SaveAs),
        ]:
            a = QAction(self.t(key, fb), self)
            a.setShortcut(seq)
            a.triggered.connect(slot)
            m_file.addAction(a)
        m_file.addSeparator()
        m_exp = m_file.addMenu(self.t("menu_export", "Экспорт"))
        for label, slot, seq in [
            ("PNG…", lambda: self.save_figure("png"), "Ctrl+Shift+P"),
            ("PDF…", lambda: self.save_figure("pdf"), "Ctrl+Shift+D"),
            ("SVG…", lambda: self.save_figure("svg"), "Ctrl+Shift+G"),
            (self.t("menu_exp_csv", "Сетка в CSV…"), self.export_grid_csv, "Ctrl+Shift+E"),
            (self.t("menu_exp_matrix", "Матрицу в CSV…"), self.export_matrix_csv, None),
        ]:
            a = QAction(label, self)
            if seq:
                a.setShortcut(seq)
            a.triggered.connect(slot)
            m_exp.addAction(a)
        m_file.addSeparator()
        a = QAction(self.t("menu_exit", "Выход"), self)
        a.setShortcut(QKeySequence.Quit)
        a.triggered.connect(self.close)
        m_file.addAction(a)

        m_set = mb.addMenu(self.t("menu_settings", "Настройки"))
        self.act_theme = QAction(self.t("menu_theme", "Тёмная тема"), self, checkable=True)
        self.act_theme.setChecked(True)
        self.act_theme.setShortcut("Ctrl+T")
        self.act_theme.triggered.connect(
            lambda on: self.apply_theme("dark" if on else "light"))
        m_set.addAction(self.act_theme)
        m_lang = m_set.addMenu(self.t("menu_lang", "Язык"))
        grp = QActionGroup(self)
        grp.setExclusive(True)
        for code, name in core.LANGS:
            a = QAction(name, self, checkable=True)
            a.setChecked(code == self.lang)
            a.triggered.connect(lambda _c=False, cc=code: self.set_language(cc))
            grp.addAction(a)
            m_lang.addAction(a)

        m_mat = mb.addMenu(self.t("menu_materials", "Материалы"))
        a = QAction(self.t("menu_lib", "База материалов…"), self)
        a.triggered.connect(self.open_library)
        m_mat.addAction(a)

        m_help = mb.addMenu(self.t("menu_help", "Справка"))
        a = QAction(self.t("menu_guide", "Руководство"), self)
        a.setShortcut("F1")
        a.triggered.connect(self.on_guide)
        m_help.addAction(a)
        a = QAction(self.t("menu_about", "О программе"), self)
        a.triggered.connect(self.on_about)
        m_help.addAction(a)

    # ---------- каркас ----------
    def _build_ui(self):
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(1)

        left_host = QWidget()
        left = QVBoxLayout(left_host)
        left.setContentsMargins(SP_L, SP_L, SP_M, SP_L)
        left.setSpacing(SP_L)
        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self._tab_process(), self.t("tab_process", "Режим"))
        self.left_tabs.addTab(self._tab_material(), self.t("tab_material", "Материал"))
        self.left_tabs.addTab(self._tab_style(), self.t("tab_style", "Оформление"))
        left.addWidget(self.left_tabs, 1)

        scroll = QScrollArea()
        scroll.setWidget(left_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(430)
        scroll.setMaximumWidth(560)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(SP_M, SP_L, SP_L, SP_L)
        rl.setSpacing(SP_L)
        self.tabs = QTabWidget()
        self.plot = PlotPane()
        self.tabs.addTab(self.plot, self.t("tab_map", "Карта"))
        self.tabs.addTab(self._tab_matrix(), self.t("tab_matrix", "План эксперимента"))
        rl.addWidget(self.tabs, 1)
        rl.addWidget(self._card_result())

        split.addWidget(scroll)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([470, 1090])
        self.setCentralWidget(split)

    # ---------- вкладка «Режим» ----------
    def _tab_process(self):
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(SP_M, SP_M, SP_M, SP_M)
        lay.setSpacing(SP_L)

        # --- процесс ---
        c_proc = self._card("grp_proc", "Процесс")
        self.rb_kin = QRadioButton(self.t("mode_kin", "Shoulderless (пруток)"))
        self.rb_shoulder = QRadioButton(self.t("mode_shoulder", "Shouldered / MELD"))
        self.rb_kin.setChecked(True)
        g = QButtonGroup(self)
        g.addButton(self.rb_kin); g.addButton(self.rb_shoulder)
        self.rb_kin.toggled.connect(self._on_mode_change)
        c_proc.body.addWidget(self.rb_kin)
        c_proc.body.addWidget(self.rb_shoulder)
        lay.addWidget(c_proc)

        # --- параметры режима ---
        c_par = self._card("grp_params", "Параметры режима")
        hdr = QHBoxLayout()
        hdr.setSpacing(SP_S)
        for key, fb, w in [(None, "", 58), ("hdr_min", "мин", 66),
                           (None, "", 12), ("hdr_max", "макс", 66),
                           ("hdr_point", "точка", 66)]:
            l = self._lbl(key, fb, hint=True) if key else QLabel("")
            l.setObjectName("Hint")
            l.setFixedWidth(w)
            l.setAlignment(Qt.AlignCenter)
            hdr.addWidget(l)
        hdr.addStretch(1)
        c_par.body.addLayout(hdr)

        self.rows = {}
        for sym in ("ω", "vz", "vx", "D", "H", "a", "F"):
            row = RangeRow(sym, core.disp_sym(sym), self._unit(sym))
            row.chk.toggled.connect(lambda on, s=sym: self._on_vary(s, on))
            for e in (row.e_min, row.e_max, row.e_pt):
                e.editingFinished.connect(self._on_edit)
            self.rows[sym] = row
            c_par.body.addWidget(row)
        lay.addWidget(c_par)

        # --- оси ---
        c_ax = self._card("grp_axes", "Оси карты")
        gl = QGridLayout()
        gl.setSpacing(SP_M)
        gl.addWidget(QLabel("X"), 0, 0)
        gl.addWidget(QLabel("Y"), 1, 0)
        self.cb_x = QComboBox(); self.cb_y = QComboBox()
        self.cb_x.currentTextChanged.connect(lambda _t: self._on_axis_change("x"))
        self.cb_y.currentTextChanged.connect(lambda _t: self._on_axis_change("y"))
        gl.addWidget(self.cb_x, 0, 1)
        gl.addWidget(self.cb_y, 1, 1)
        gl.setColumnStretch(1, 1)
        c_ax.body.addLayout(gl)

        self.lbl_fixed = QLabel("")
        self.lbl_fixed.setObjectName("Hint")
        self.lbl_fixed.setWordWrap(True)
        c_ax.body.addWidget(self.lbl_fixed)
        lay.addWidget(c_ax)

        # --- дополнительно ---
        c_ex = self._card("grp_extra", "Дополнительно")
        self.chk_feed = self._chk("chk_feedsink", "Сток подачи ρcₚ·V̇")
        self.chk_pe = self._chk("chk_pe", "Скоростная поправка G(Pe)")
        self.chk_tdep = self._chk("chk_tdep", "k, cₚ зависят от T")
        self.chk_bore = self._chk("chk_bore", "Кольцевой контакт плеча")
        for c, attr in [(self.chk_feed, "use_feedsink"), (self.chk_pe, "use_pe"),
                        (self.chk_tdep, "use_tdep"), (self.chk_bore, "bore")]:
            c.toggled.connect(lambda on, a=attr: self._set_flag(a, on))
            c_ex.body.addWidget(c)
        self.f_rodL = self._field("lbl_rodl", "L, вылет прутка", 0, "мм")
        self.f_rodL.edit.editingFinished.connect(self._on_edit)
        c_ex.body.addWidget(self.f_rodL)
        lay.addWidget(c_ex)

        row = QHBoxLayout()
        row.setSpacing(SP_M)
        btn = self._btn("btn_point", "Рассчитать точку", accent=True)
        btn.clicked.connect(self.calc_point)
        row.addWidget(btn, 1)
        b_clr = self._btn("btn_clearpts", "Очистить точки")
        b_clr.clicked.connect(self.clear_points)
        row.addWidget(b_clr, 0)
        lay.addLayout(row)
        lay.addStretch(1)
        return host

    # ---------- вкладка «Материал» ----------
    def _tab_material(self):
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(SP_M, SP_M, SP_M, SP_M)
        lay.setSpacing(SP_L)

        c_dep = self._card("grp_dep", "Пруток (присадка)")
        self.cb_material = QComboBox()
        self.cb_material.addItems(sorted(self.st.materials.keys()))
        self.cb_material.setCurrentText(self.st.preset)
        self.cb_material.currentTextChanged.connect(self._on_material)
        c_dep.body.addWidget(self.cb_material)

        self.mat_fields = {}
        for key, label, unit in [
            ("sigma_ref", "σ_ref", "МПа"), ("T_ref", "T_ref", "°C"),
            ("m", "m", ""), ("T_solidus", "T solidus", "°C"),
            ("T0", "T₀", "°C"), ("rho", "ρ", "кг/м³"),
            ("cp", "cₚ", "Дж/(кг·К)"), ("k", "k", "Вт/(м·К)"),
        ]:
            f = Field(label, self.st.fields.get(key, ""), unit)
            f.edit.editingFinished.connect(self._on_edit)
            self.mat_fields[key] = f
            c_dep.body.addWidget(f)
        lay.addWidget(c_dep)

        c_sub = self._card("grp_sub", "Подложка")
        self.chk_subsame = self._chk("chk_subsame", "= материал прутка")
        self.chk_subsame.setChecked(True)
        self.chk_subsame.toggled.connect(self._on_subsame)
        c_sub.body.addWidget(self.chk_subsame)
        self.cb_substrate = QComboBox()
        self.cb_substrate.addItems(sorted(self.st.materials.keys()))
        self.cb_substrate.setCurrentText(self.st.substrate)
        self.cb_substrate.currentTextChanged.connect(self._on_substrate)
        c_sub.body.addWidget(self.cb_substrate)
        for key, label, unit in [("k_sub", "k", "Вт/(м·К)"),
                                 ("rho_sub", "ρ", "кг/м³"),
                                 ("cp_sub", "cₚ", "Дж/(кг·К)")]:
            f = Field(label, self.st.fields.get(key, ""), unit)
            f.edit.editingFinished.connect(self._on_edit)
            self.mat_fields[key] = f
            c_sub.body.addWidget(f)
        lay.addWidget(c_sub)

        c_fr = self._card("grp_friction", "Контакт")
        self.f_mu = Field("μ", self.st.fields.get("mu", "0.5"), "")
        self.f_mu.edit.editingFinished.connect(self._on_edit)
        c_fr.body.addWidget(self.f_mu)
        self.chk_mutdep = self._chk("chk_mutdep", "μ зависит от T (таблица пары)")
        self.chk_mutdep.toggled.connect(self._on_mutdep)
        c_fr.body.addWidget(self.chk_mutdep)
        self.cb_mupair = QComboBox()
        self.cb_mupair.addItems([core.MU_PAIR_NONE] + sorted(self.st.mu_tables.keys()))
        self.cb_mupair.setEnabled(False)
        self.cb_mupair.currentTextChanged.connect(self._on_mupair)
        c_fr.body.addWidget(self.cb_mupair)
        self.f_kshoe = self._field("lbl_kshoe", "k плеча",
                                   self.st.fields.get("k_shoe", "25"), "Вт/(м·К)")
        self.f_kshoe.edit.editingFinished.connect(self._on_edit)
        c_fr.body.addWidget(self.f_kshoe)
        lay.addWidget(c_fr)
        lay.addStretch(1)
        return host

    # ---------- вкладка «Оформление» ----------
    def _tab_style(self):
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(SP_M, SP_M, SP_M, SP_M)
        lay.setSpacing(SP_L)

        c_view = self._card("grp_view", "Вид")
        row = QHBoxLayout()
        self.rb_2d = QRadioButton("2D"); self.rb_3d = QRadioButton("3D")
        self.rb_2d.setChecked(True)
        g = QButtonGroup(self); g.addButton(self.rb_2d); g.addButton(self.rb_3d)
        self.rb_2d.toggled.connect(self._on_view_change)
        row.addWidget(self.rb_2d); row.addWidget(self.rb_3d); row.addStretch(1)
        c_view.body.addLayout(row)
        self.chk_winfill = self._chk("chk_winfill", "Подсветить окно")
        self.chk_winfill.toggled.connect(lambda _v: self.rebuild())
        c_view.body.addWidget(self.chk_winfill)
        lay.addWidget(c_view)

        c_win = self._card("grp_window", "Технологическое окно")
        self.sp_wlo = QDoubleSpinBox(); self.sp_whi = QDoubleSpinBox()
        for sp, val in ((self.sp_wlo, 0.6), (self.sp_whi, 0.9)):
            sp.setRange(0.05, 1.5); sp.setSingleStep(0.05); sp.setDecimals(2)
            sp.setValue(val)
            sp.valueChanged.connect(self._on_window)
        r = QHBoxLayout()
        r.addWidget(QLabel("×T_s:")); r.addWidget(self.sp_wlo)
        r.addWidget(QLabel("…")); r.addWidget(self.sp_whi); r.addStretch(1)
        c_win.body.addLayout(r)
        lay.addWidget(c_win)

        c_txt = self._card("grp_text", "Текст и сетка")
        self.sp_fs = QSpinBox(); self.sp_fs.setRange(6, 28); self.sp_fs.setValue(13)
        self.sp_fs.valueChanged.connect(lambda _v: self.redraw())
        r = QHBoxLayout(); r.addWidget(self._lbl("lbl_fs", "Размер текста"))
        r.addWidget(self.sp_fs); r.addStretch(1)
        c_txt.body.addLayout(r)

        self.sp_lev = QSpinBox(); self.sp_lev.setRange(6, 60); self.sp_lev.setValue(24)
        self.sp_lev.valueChanged.connect(lambda _v: self.redraw())
        r = QHBoxLayout(); r.addWidget(self._lbl("lbl_levels", "Градаций цвета"))
        r.addWidget(self.sp_lev); r.addStretch(1)
        c_txt.body.addLayout(r)

        self.sp_n3d = QSpinBox(); self.sp_n3d.setRange(16, 160); self.sp_n3d.setValue(48)
        self.sp_n3d.valueChanged.connect(lambda _v: self.rebuild())
        r = QHBoxLayout(); r.addWidget(self._lbl("lbl_n3d", "Сетка 3D"))
        r.addWidget(self.sp_n3d); r.addStretch(1)
        c_txt.body.addLayout(r)
        lay.addWidget(c_txt)

        c_3d = self._card("grp_3d", "Ракурс 3D")
        self.sl_elev = QSlider(Qt.Horizontal); self.sl_elev.setRange(-90, 90)
        self.sl_elev.setValue(28)
        self.sl_azim = QSlider(Qt.Horizontal); self.sl_azim.setRange(-180, 180)
        self.sl_azim.setValue(-130)
        for s in (self.sl_elev, self.sl_azim):
            s.valueChanged.connect(self._on_view_angle)
        r = QHBoxLayout(); r.addWidget(self._lbl("lbl_elev", "Подъём"))
        r.addWidget(self.sl_elev, 1); c_3d.body.addLayout(r)
        r = QHBoxLayout(); r.addWidget(self._lbl("lbl_azim", "Азимут"))
        r.addWidget(self.sl_azim, 1); c_3d.body.addLayout(r)
        lay.addWidget(c_3d)
        lay.addStretch(1)
        return host

    # ---------- вкладка «План эксперимента» ----------
    def _tab_matrix(self):
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(SP_M, SP_M, SP_M, SP_M)
        lay.setSpacing(SP_M)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)

        c_reg = self._card("reg_eq_title", "Регрессия T_peak")
        self.txt_reg = QTextEdit()
        self.txt_reg.setReadOnly(True)
        self.txt_reg.setMaximumHeight(96)
        c_reg.body.addWidget(self.txt_reg)
        r = QHBoxLayout()
        b = self._btn("btn_copyreg_full", "Копировать LaTeX")
        b.clicked.connect(self.copy_latex)
        r.addWidget(b)
        b = self._btn("mat_export", "Экспорт CSV")
        b.clicked.connect(self.export_matrix_csv)
        r.addWidget(b); r.addStretch(1)
        c_reg.body.addLayout(r)
        lay.addWidget(c_reg)
        return host

    def _card_result(self):
        card = Card()
        self.lbl_result = QLabel("—")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # результат выводится увеличенным кеглем через rich text; QLabel считает
        # высоту по шрифту виджета, а не по разметке, поэтому задаём минимум
        self.lbl_result.setMinimumHeight(58)
        self.lbl_result.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("Hint")
        self.lbl_hint.setWordWrap(True)
        card.body.addWidget(self.lbl_result)
        card.body.addWidget(self.lbl_hint)
        return card

    # ---------- создание переводимых виджетов ----------
    def _card(self, key, fallback):
        """Карточка, заголовок которой обновится при смене языка."""
        c = Card(self.t(key, fallback))
        self._titled_cards.append((c, key, fallback))
        return c

    def _chk(self, key, fallback):
        c = QCheckBox(self.t(key, fallback))
        self._texted.append((c, key, fallback))
        return c

    def _btn(self, key, fallback, accent=False):
        b = QPushButton(self.t(key, fallback))
        if accent:
            b.setObjectName("Accent")
        self._texted.append((b, key, fallback))
        return b

    def _lbl(self, key, fallback, hint=False):
        l = QLabel(self.t(key, fallback))
        if hint:
            l.setObjectName("Hint")
        self._texted.append((l, key, fallback))
        return l

    def _field(self, key, fallback, value="", unit=""):
        f = Field(self.t(key, fallback), value, unit)
        self._labeled_fields.append((f, key, fallback))
        return f

    # ---------- единицы ----------
    def _unit(self, sym):
        return self.t(core.AX_UNIT_KEY.get(sym, ""), "")

    def _axis_label(self, sym):
        name, math_sym, unit = core.JLAB[sym]
        return "$%s$, %s" % (math_sym, unit)

    # ---------- состояние <-> виджеты ----------
    def _state_to_widgets(self):
        """Заполнить виджеты из модели (после загрузки проекта/смены режима)."""
        self._building = True
        try:
            st = self.st
            self.rb_kin.setChecked(st.input_mode == "kin")
            self.rb_shoulder.setChecked(st.input_mode == "shoulder")
            cands = st.candidates()
            for sym, row in self.rows.items():
                on = sym in cands
                row.setVisible(on)
                if not on:
                    continue
                row.chk.setChecked(st.vary.get(sym) == "range")
                row.set_range_mode(st.vary.get(sym) == "range")
                lo_key, hi_key = core.RANGE_KEYS[sym]
                row.e_min.setText(str(st.fields.get(lo_key, "")))
                row.e_max.setText(str(st.fields.get(hi_key, "")))
                row.e_pt.setText(str(st.fields.get(core.PT_KEY[sym], "")))
                row.lbl_unit.setText(self._unit(sym))
            for key, f in self.mat_fields.items():
                f.set_value(st.fields.get(key, ""))
            self.f_mu.set_value(st.fields.get("mu", "0.5"))
            self.f_rodL.set_value(st.fields.get("rod_L", "0"))
            self.f_kshoe.set_value(st.fields.get("k_shoe", "25"))
            self.cb_material.setCurrentText(st.preset)
            self.cb_substrate.setCurrentText(st.substrate)
            self.chk_subsame.setChecked(st.sub_same)
            self.cb_substrate.setEnabled(not st.sub_same)
            self.chk_feed.setChecked(st.use_feedsink)
            self.chk_pe.setChecked(st.use_pe)
            self.chk_tdep.setChecked(st.use_tdep)
            self.chk_bore.setChecked(st.bore)
            self.chk_mutdep.setChecked(st.mu_tdep)
            self.cb_mupair.setCurrentText(st.mu_pair)
            self.cb_mupair.setEnabled(st.mu_tdep)
            self.sp_wlo.setValue(st.wlo)
            self.sp_whi.setValue(st.whi)
            self._refresh_axes()
        finally:
            self._building = False

    def _widgets_to_state(self):
        """Считать значения полей в модель."""
        st = self.st
        for sym, row in self.rows.items():
            if sym not in st.candidates():
                continue
            lo_key, hi_key = core.RANGE_KEYS[sym]
            st.fields[lo_key] = row.e_min.text()
            st.fields[hi_key] = row.e_max.text()
            st.fields[core.PT_KEY[sym]] = row.e_pt.text()
        for key, f in self.mat_fields.items():
            st.fields[key] = f.text()
        st.fields["mu"] = self.f_mu.text()
        st.fields["rod_L"] = self.f_rodL.text()
        st.fields["k_shoe"] = self.f_kshoe.text()

    def _refresh_axes(self):
        """Список осей = варьируемые параметры; поддерживаем X ≠ Y."""
        st = self.st
        order = st.order()
        st.ensure_axes()
        for cb, cur in ((self.cb_x, st.xaxis), (self.cb_y, st.yaxis)):
            cb.blockSignals(True)
            cb.clear()
            cb.addItems([core.disp_sym(s) for s in order])
            if cur in order:
                cb.setCurrentIndex(order.index(cur))
            cb.blockSignals(False)
        fixed = [s for s in st.candidates() if s not in (st.xaxis, st.yaxis)]
        self.lbl_fixed.setText(
            self.t("lbl_held", "Удерживаются: ") +
            ", ".join("%s=%g" % (core.disp_sym(s), st.fix.get(s, 0.0)) for s in fixed))

    # ---------- обработчики ----------
    def _on_edit(self):
        if self._building:
            return
        self._widgets_to_state()
        self.rebuild()

    def _on_vary(self, sym, on):
        if self._building:
            return
        self.st.vary[sym] = "range" if on else "fixed"
        self.rows[sym].set_range_mode(on)
        self._refresh_axes()
        self.rebuild()

    def _set_flag(self, attr, on):
        if self._building:
            return
        setattr(self.st, attr, bool(on))
        self.rebuild()

    def _on_mode_change(self):
        if self._building:
            return
        self.st.input_mode = "kin" if self.rb_kin.isChecked() else "shoulder"
        self._state_to_widgets()
        self.rebuild()

    def _on_material(self, name):
        if self._building:
            return
        self.st.load_preset(name)
        self._state_to_widgets()
        self.rebuild()

    def _on_substrate(self, name):
        if self._building:
            return
        self.st.substrate = name
        m = self.st.materials.get(name, {})
        for key, src in (("k_sub", "k"), ("rho_sub", "rho"), ("cp_sub", "cp")):
            if src in m:
                self.st.fields[key] = str(m[src])
        self._state_to_widgets()
        self.rebuild()

    def _on_subsame(self, on):
        if self._building:
            return
        self.st.sub_same = bool(on)
        self.cb_substrate.setEnabled(not on)
        self.rebuild()

    def _on_mutdep(self, on):
        if self._building:
            return
        self.st.mu_tdep = bool(on)
        self.cb_mupair.setEnabled(bool(on))
        self.rebuild()

    def _on_mupair(self, name):
        if self._building:
            return
        self.st.mu_pair = name
        self.rebuild()

    def _on_axis_change(self, which):
        if self._building:
            return
        order = self.st.order()
        idx = self.cb_x.currentIndex() if which == "x" else self.cb_y.currentIndex()
        if not (0 <= idx < len(order)):
            return
        if which == "x":
            self.st.xaxis = order[idx]
        else:
            self.st.yaxis = order[idx]
        # X и Y не должны совпадать
        if self.st.xaxis == self.st.yaxis:
            alt = [s for s in order if s != self.st.xaxis]
            if alt:
                if which == "x":
                    self.st.yaxis = alt[0]
                else:
                    self.st.xaxis = alt[0]
        self._building = True
        self._refresh_axes()
        self._building = False
        self.rebuild()

    def _on_window(self):
        if self._building:
            return
        self.st.wlo = self.sp_wlo.value()
        self.st.whi = self.sp_whi.value()
        self.redraw()

    def _on_view_change(self):
        if self._building:
            return
        self.view = "2D" if self.rb_2d.isChecked() else "3D"
        self.rebuild()

    def _on_view_angle(self):
        if self.view != "3D" or self._building:
            return
        for ax in self.plot.fig.get_axes():
            if hasattr(ax, "view_init"):
                ax.view_init(elev=self.sl_elev.value(), azim=self.sl_azim.value())
        self.plot.canvas.draw_idle()

    # ---------- тема ----------
    def apply_theme(self, name):
        self.theme_name = name
        pal = THEMES[name]
        self.pal = pal
        QApplication.instance().setStyleSheet(qss(pal))
        matplotlib.rcParams.update(mpl_rc(pal))
        if hasattr(self, "act_theme"):
            self.act_theme.setChecked(name == "dark")
        self.redraw()

    def set_language(self, code):
        self.lang = code
        self.retranslate()

    def retranslate(self):
        """Перевести надписи на месте.

        Меню пересобирается целиком (у QAction нет обратной связи с ключом),
        остальное правится по ссылкам на виджеты — так не теряются введённые
        значения и текущая вкладка."""
        self.menuBar().clear()
        self._build_menu()

        self.left_tabs.setTabText(0, self.t("tab_process", "Режим"))
        self.left_tabs.setTabText(1, self.t("tab_material", "Материал"))
        self.left_tabs.setTabText(2, self.t("tab_style", "Оформление"))
        self.tabs.setTabText(0, self.t("tab_map", "Карта"))
        self.tabs.setTabText(1, self.t("tab_matrix", "План эксперимента"))

        for card, key, fb in self._titled_cards:
            card.set_title(self.t(key, fb))
        for w, key, fb in self._texted:
            w.setText(self.t(key, fb))
        for f, key, fb in self._labeled_fields:
            f.set_label(self.t(key, fb))

        self.rb_kin.setText(self.t("mode_kin", "Shoulderless (пруток)"))
        self.rb_shoulder.setText(self.t("mode_shoulder", "Shouldered / MELD"))
        self._update_title()
        for sym, row in self.rows.items():
            row.lbl_unit.setText(self._unit(sym))
        self._refresh_axes()
        self._refresh_matrix()
        self.redraw()
        self.statusBar().showMessage(self.t("menu_lang", "Язык") + ": " + self.lang, 2000)

    # ---------- расчёт и отрисовка ----------
    def rebuild(self):
        """Пересчитать сетку и перерисовать."""
        if self._building:
            return
        try:
            n = self.sp_n3d.value() if self.view == "3D" else 140
            g = self.st.grid(n=n)
        except Exception as exc:
            self.statusBar().showMessage("%s: %s" % (self.t("err", "Ошибка"), exc), 4000)
            g = None
        self._last_grid = g
        if g is None:
            # Карте нужны две оси, но плану 3^N хватает и одного фактора —
            # таблица и регрессия обновляются в любом случае.
            self.statusBar().showMessage(
                self.t("need2range", "Для карты нужно ≥2 варьируемых параметра"), 4000)
            self.plot.fig.clf()
            self.plot.canvas.draw_idle()
        else:
            self.redraw()
        self._refresh_matrix()

    def redraw(self):
        """Перерисовать по уже посчитанной сетке."""
        g = self._last_grid
        if not g:
            return
        xN, yN, xv, yv, T, fixed = g
        try:
            Tmin, Tmax = self.st.window()
        except Exception:
            return
        pal = self.pal
        fs = self.sp_fs.value()
        self.plot.fig.clf()
        X, Y = np.meshgrid(xv, yv)
        if self.view == "3D":
            self._draw_3d(X, Y, T, xN, yN, Tmin, Tmax, fs)
        else:
            self._draw_2d(X, Y, T, xN, yN, Tmin, Tmax, fs)
        self.plot.style_axes(pal)

    def _draw_2d(self, X, Y, T, xN, yN, Tmin, Tmax, fs):
        pal = self.pal
        ax = self.plot.fig.add_subplot(111)
        cs = ax.contourf(X, Y, T, levels=self.sp_lev.value(), cmap="magma")
        if self.chk_winfill.isChecked():
            mask = np.where((T >= Tmin) & (T <= Tmax), 1.0, np.nan)
            ax.contourf(X, Y, mask, levels=[0.5, 1.5], colors=["#19d219"], alpha=0.28)
        # границы окна: гомологическая температура — отношение абсолютных,
        # поэтому в подписи и доля, и её значение в °C
        for lev, col, frac in ((Tmin, pal.accent, self.st.wlo),
                               (Tmax, pal.danger, self.st.whi)):
            try:
                c = ax.contour(X, Y, T, levels=[lev], colors=col,
                               linewidths=1.8, linestyles="--")
                ax.clabel(c, fmt={lev: "$T/T_s=%g$ (%.0f)" % (frac, lev)},
                          fontsize=max(6, fs - 2))
            except Exception:
                pass
        cb = self.plot.fig.colorbar(cs, ax=ax, pad=0.02)
        cb.set_label("$T_{peak}$, °C", color=pal.text, fontsize=fs)
        cb.ax.tick_params(colors=pal.text_dim, labelsize=max(6, fs - 2))
        ax.set_xlabel(self._axis_label(xN), fontsize=fs)
        ax.set_ylabel(self._axis_label(yN), fontsize=fs)
        ax.tick_params(labelsize=max(6, fs - 2))
        self._draw_points(ax, xN, yN, fs)
        self.plot.fig.tight_layout()

    def _draw_3d(self, X, Y, T, xN, yN, Tmin, Tmax, fs):
        pal = self.pal
        ax = self.plot.fig.add_subplot(111, projection="3d")
        ax.plot_surface(X, Y, T, cmap="magma", rstride=1, cstride=1,
                        linewidth=0, antialiased=True, alpha=0.96)
        try:                       # плоскости границ окна — где режим допустим
            ax.contour(X, Y, T, levels=[Tmin, Tmax], colors=[pal.accent, pal.danger],
                       linewidths=1.4, linestyles="--", offset=float(np.nanmin(T)))
        except Exception:
            pass
        ax.set_xlabel(self._axis_label(xN), fontsize=fs, labelpad=8)
        ax.set_ylabel(self._axis_label(yN), fontsize=fs, labelpad=8)
        ax.set_zlabel("$T_{peak}$, °C", fontsize=fs, labelpad=8)
        ax.tick_params(labelsize=max(6, fs - 3))
        ax.view_init(elev=self.sl_elev.value(), azim=self.sl_azim.value())
        self.plot.fig.tight_layout()

    def calc_point(self):
        self._widgets_to_state()
        try:
            T, aud, vals = self.st.point()
            Tmin, Tmax = self.st.window()
        except Exception as exc:
            QMessageBox.critical(self, self.t("err", "Ошибка"), str(exc))
            return
        inside = Tmin <= T <= Tmax
        col = self.pal.ok if inside else self.pal.danger
        status = (self.t("st_in", "в окне") if inside else
                  (self.t("st_below", "ниже окна") if T < Tmin
                   else self.t("st_above", "выше окна")))
        self.lbl_result.setText(
            '<span style="font-size:15pt;font-weight:600">T_peak = %.1f °C</span>'
            '<span style="color:%s">  (%.1f K)</span>'
            '<br><span style="color:%s">%s %.0f…%.0f °C</span>'
            % (T, self.pal.text_dim, core.c_to_k(T), col, status, Tmin, Tmax))
        extra = ("%s: %s   τ_c=%.1f МПа   p=%.1f МПа   μ=%.3f   Q=%.0f Вт   Pe=%.2f"
                 % (self.t("lbl_regime", "режим"), aud["branch"], aud["tau_c"],
                    aud["p_contact"], aud["mu_eff"], aud["Q"], aud["Pe"]))
        if aud.get("sink_rod", 0.0) > 0:
            extra += "   η_экв=%.2f" % aud.get("eta_rod", 1.0)
        if aud.get("solidus_flag"):
            extra += "   ⚠ " + self.t("flag_solidus", "выше солидуса")
        self.lbl_hint.setText(extra)

        # накапливаем точки: новая не убирает прежние, ей даётся следующая буква.
        # повтор того же набора параметров не плодит дубликат.
        newvals = {k: float(v) for k, v in vals.items()}
        if self._points and self._points[-1]["vals"] == newvals:
            self._points[-1]["T"] = float(T)
        else:
            self._points.append({"label": self._next_label(),
                                 "vals": newvals, "T": float(T)})
        self.redraw()

    def _next_label(self):
        """Следующая свободная буква: A, B, … Z, AA, AB, …"""
        used = {p["label"] for p in self._points}
        letters = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        for c in letters + [a + b for a in letters for b in letters]:
            if c not in used:
                return c
        return "P%d" % (len(self._points) + 1)

    def clear_points(self):
        self._points = []
        self.redraw()

    def _draw_points(self, ax, xN, yN, fs):
        """Отметить на карте рассчитанные точки — только те, что попадают в оси."""
        for p in self._points:
            vals = p["vals"]
            if xN not in vals or yN not in vals:
                continue
            ax.plot(vals[xN], vals[yN], "o", ms=8, mfc="white", mec="black",
                    mew=1.4, zorder=40)
            # у правого края подпись уходила бы за поле графика — отражаем её влево
            x0, x1 = ax.get_xlim()
            near_right = (vals[xN] - x0) > 0.82 * (x1 - x0)
            ax.annotate("%s  %.0f°C" % (p["label"], p["T"]),
                        (vals[xN], vals[yN]), textcoords="offset pixels",
                        xytext=(-12, 0) if near_right else (12, 0),
                        ha="right" if near_right else "left", va="center",
                        fontsize=max(7, fs - 2), fontweight="bold",
                        color="black", zorder=41,
                        bbox=dict(boxstyle="round,pad=0.25", fc="white",
                                  ec="0.4", alpha=0.95))

    def _refresh_matrix(self):
        """Таблица плана 3^N и уравнение регрессии."""
        try:
            rows = self.st.matrix_rows()
            order = self.st.order()
        except Exception as exc:
            self.txt_reg.setPlainText(str(exc))
            return
        if not rows:
            self.table.setRowCount(0)
            self.txt_reg.setPlainText(
                self.t("need2range", "Нужен хотя бы один варьируемый параметр"))
            return
        heads = (["№"] + ["X%d" % (i + 1) for i in range(len(order))]
                 + [core.disp_sym(s) for s in order]
                 + ["τ, МПа", "T_peak, °C", "T_peak, K"])
        self.table.setColumnCount(len(heads))
        self.table.setHorizontalHeaderLabels(heads)
        self.table.setRowCount(len(rows))
        for i, (n, codes, reals, tau, Tc, Tk) in enumerate(rows):
            vals = ([str(n)] + ["%+d" % c if c else "0" for c in codes]
                    + ["%g" % v for v in reals]
                    + ["%.2f" % tau, "%.1f" % Tc, "%.1f" % Tk])
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, j, it)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        try:
            fit = self.st.fit_regression()
            if fit:
                c0, lin, quad, inter, order = fit
                text = core.poly_text(c0, lin, quad, inter,
                                      [core.UNI[s] for s in order])
                units = "[ " + ";  ".join("%s: %s" % (core.UNI.get(s, s), self._unit(s))
                                          for s in order) + " ]"
                self.txt_reg.setPlainText(text + "\n" + units)
                self._latex = self._regression_latex(c0, lin, quad, inter,
                                                     [core.AX_MATH[s] for s in order])
        except Exception as exc:
            self.txt_reg.setPlainText(str(exc))

    @staticmethod
    def _regression_latex(c0, lin, quad, inter, syms):
        """Уравнение в LaTeX — для вставки в статью."""
        import itertools as it
        N = len(syms)
        terms = [(c0, "")]
        terms += [(lin[j], syms[j]) for j in range(N)]
        terms += [(quad[j], syms[j] + "^{2}") for j in range(N)]
        pairs = list(it.combinations(range(N), 2))
        terms += [(inter[i], syms[a] + r"\," + syms[b]) for i, (a, b) in enumerate(pairs)]
        out, first = "", True
        for coef, sym in terms:
            if coef == 0:
                continue
            sign = "-" if coef < 0 else "+"
            body = (r"%g\,%s" % (abs(coef), sym)) if sym else "%g" % abs(coef)
            out += (("-" if sign == "-" else "") + body) if first else " %s %s" % (sign, body)
            first = False
        return r"T_{\mathrm{peak}} = " + (out if out else "0")

    def copy_latex(self):
        tex = getattr(self, "_latex", None)
        if not tex:
            self.statusBar().showMessage(self.t("no_data", "Нет данных"), 2500)
            return
        QGuiApplication.clipboard().setText(tex)
        self.statusBar().showMessage(self.t("copied", "Скопировано в буфер"), 2500)

    # ---------- проект ----------
    def on_new(self):
        self.st = core.ModelState()
        self._project_path = None
        self._points = []
        self._state_to_widgets()
        self.rebuild()
        self._mark_saved()
        self._update_title()

    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.t("menu_open", "Открыть проект"), "",
            "AFSD project (*.afsd);;JSON (*.json);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.st.from_dict(data)
        except Exception as exc:
            QMessageBox.critical(self, self.t("err", "Ошибка"), str(exc))
            return
        self._project_path = path
        self._state_to_widgets()
        self.rebuild()
        self._mark_saved()
        self._update_title()

    def on_save(self):
        if self._project_path:
            self._write_project(self._project_path)
        else:
            self.on_save_as()

    def on_save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.t("menu_saveas", "Сохранить проект"),
            self._project_path or "project.afsd",
            "AFSD project (*.afsd);;JSON (*.json)")
        if not path:
            return
        if self._write_project(path):
            self._project_path = path
            self._update_title()

    def _write_project(self, path):
        self._widgets_to_state()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.st.to_dict(), fh, ensure_ascii=False, indent=1)
        except Exception as exc:
            QMessageBox.critical(self, self.t("err", "Ошибка"), str(exc))
            return False
        self._mark_saved()
        self._update_title()
        self.statusBar().showMessage("%s: %s" % (self.t("saved", "Сохранено"), path), 3000)
        return True

    def _update_title(self):
        name = os.path.basename(self._project_path) if self._project_path else ""
        star = "" if self._is_saved() else " *"
        base = "%s — %s" % (core.APP_NAME, name) if name else core.APP_NAME
        self.setWindowTitle(base + star)

    def _mark_saved(self):
        """Запомнить текущее состояние как сохранённое."""
        self._widgets_to_state()
        self._saved_snapshot = json.dumps(self.st.to_dict(), sort_keys=True)

    def _is_saved(self):
        snap = getattr(self, "_saved_snapshot", None)
        if snap is None:
            return True
        try:
            self._widgets_to_state()
            return json.dumps(self.st.to_dict(), sort_keys=True) == snap
        except Exception:
            return True

    def closeEvent(self, event):
        """Не терять несохранённую работу молча."""
        if self._is_saved():
            event.accept()
            return
        r = QMessageBox.question(
            self, core.APP_NAME,
            self.t("ask_save", "Проект изменён. Сохранить перед выходом?"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            event.ignore()
        elif r == QMessageBox.Save:
            self.on_save()
            event.accept() if self._is_saved() else event.ignore()
        else:
            event.accept()

    # ---------- экспорт ----------
    def save_figure(self, ext):
        path, _ = QFileDialog.getSaveFileName(
            self, self.t("menu_export", "Экспорт") + " " + ext.upper(),
            "afsd_map." + ext, "%s (*.%s)" % (ext.upper(), ext))
        if not path:
            return
        try:
            # экспорт всегда на белом фоне: тёмная тема нужна на экране,
            # а рисунок идёт в статью
            self.plot.fig.savefig(path, dpi=300, facecolor="white",
                                  bbox_inches="tight")
        except Exception as exc:
            QMessageBox.critical(self, self.t("err", "Ошибка"), str(exc))
            return
        self.statusBar().showMessage("%s: %s" % (self.t("saved", "Сохранено"), path), 3000)

    def export_grid_csv(self):
        if not self._last_grid:
            QMessageBox.warning(self, self.t("no_data", "Нет данных"),
                                self.t("no_data_msg", "Сначала постройте карту"))
            return
        path, _ = QFileDialog.getSaveFileName(self, self.t("menu_exp_csv", "Сетка в CSV"),
                                              "afsd_grid.csv", "CSV (*.csv)")
        if not path:
            return
        xN, yN, xv, yv, T, fixed = self._last_grid
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# fixed: %s\n" % "; ".join("%s=%g" % (s, v)
                                                     for s, v in fixed.items()))
                fh.write("%s,%s,Tpeak_C,Tpeak_K\n" % (xN, yN))
                for j, yy in enumerate(yv):
                    for i, xx in enumerate(xv):
                        fh.write("%.4f,%.4f,%.3f,%.3f\n"
                                 % (xx, yy, T[j, i], core.c_to_k(T[j, i])))
        except Exception as exc:
            QMessageBox.critical(self, self.t("err", "Ошибка"), str(exc))
            return
        self.statusBar().showMessage("%s: %s" % (self.t("saved", "Сохранено"), path), 3000)

    def export_matrix_csv(self):
        try:
            rows = self.st.matrix_rows()
            order = self.st.order()
        except Exception as exc:
            QMessageBox.critical(self, self.t("err", "Ошибка"), str(exc))
            return
        if not rows:
            QMessageBox.warning(self, self.t("no_data", "Нет данных"),
                                self.t("no_data_msg", "Нет варьируемых параметров"))
            return
        path, _ = QFileDialog.getSaveFileName(self, self.t("menu_exp_matrix", "Матрица в CSV"),
                                              "afsd_design_matrix.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                head = (["run"] + ["X%d" % (i + 1) for i in range(len(order))]
                        + list(order) + ["tau_MPa", "Tpeak_C", "Tpeak_K"])
                fh.write(",".join(head) + "\n")
                for n, codes, reals, tau, Tc, Tk in rows:
                    fh.write(",".join([str(n)] + [str(c) for c in codes]
                                      + ["%g" % v for v in reals]
                                      + ["%.4f" % tau, "%.3f" % Tc, "%.3f" % Tk]) + "\n")
        except Exception as exc:
            QMessageBox.critical(self, self.t("err", "Ошибка"), str(exc))
            return
        self.statusBar().showMessage("%s: %s" % (self.t("saved", "Сохранено"), path), 3000)

    # ---------- база материалов ----------
    def open_library(self):
        dlg = MaterialDialog(self, self.st)
        if dlg.exec() == QDialog.Accepted:
            self.st.materials = core.all_materials()
            cur = self.cb_material.currentText()
            for cb in (self.cb_material, self.cb_substrate):
                cb.blockSignals(True)
                cb.clear()
                cb.addItems(sorted(self.st.materials.keys()))
                cb.blockSignals(False)
            self.cb_material.setCurrentText(cur if cur in self.st.materials
                                            else core.DEFAULT_PRESET)
            self.rebuild()

    # ---------- справка ----------
    def on_guide(self):
        txt = core.GUIDE_TEXT.get(self.lang) or core.GUIDE_TEXT.get("en", "")
        d = QDialog(self)
        d.setWindowTitle(self.t("menu_guide", "Руководство"))
        d.resize(760, 620)
        lay = QVBoxLayout(d)
        te = QTextEdit(); te.setReadOnly(True); te.setPlainText(txt)
        lay.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(d.reject); bb.accepted.connect(d.accept)
        lay.addWidget(bb)
        d.exec()

    def on_about(self):
        txt = core.ABOUT_TEXT.get(self.lang) or core.ABOUT_TEXT.get("en", "")
        QMessageBox.about(self, self.t("menu_about", "О программе"), txt)


# ---------------------------------------------------------------------------
#  диалог базы материалов
# ---------------------------------------------------------------------------
class MaterialDialog(QDialog):
    """Просмотр и правка пользовательских материалов."""

    KEYS = [("sigma_ref", "σ_ref, МПа"), ("T_ref", "T_ref, °C"), ("m", "m"),
            ("k", "k, Вт/(м·К)"), ("T_solidus", "T solidus, °C"),
            ("T0", "T₀, °C"), ("rho", "ρ, кг/м³"), ("cp", "cₚ, Дж/(кг·К)")]

    def __init__(self, parent, state):
        super().__init__(parent)
        self.st = state
        self.setWindowTitle(parent.t("menu_lib", "База материалов"))
        self.resize(720, 560)
        lay = QHBoxLayout(self)

        left = QVBoxLayout()
        self.list = QTableWidget()
        self.list.setColumnCount(1)
        self.list.setHorizontalHeaderLabels([parent.t("mat_name", "Материал")])
        self.list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list.verticalHeader().setVisible(False)
        self.list.itemSelectionChanged.connect(self._load_selected)
        left.addWidget(self.list, 1)
        lay.addLayout(left, 1)

        right = QVBoxLayout()
        self.f_name = Field(parent.t("mat_name", "Название"), "", "", width=190)
        right.addWidget(self.f_name)
        self.fields = {}
        for key, label in self.KEYS:
            f = Field(label, "", "")
            self.fields[key] = f
            right.addWidget(f)
        right.addStretch(1)
        btns = QHBoxLayout()
        b = QPushButton(parent.t("mat_save", "Сохранить"))
        b.setObjectName("Accent")
        b.clicked.connect(self._save)
        btns.addWidget(b)
        b = QPushButton(parent.t("mat_del", "Удалить"))
        b.clicked.connect(self._delete)
        btns.addWidget(b)
        right.addLayout(btns)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.accept)
        right.addWidget(bb)
        lay.addLayout(right, 1)
        self._reload()

    def _reload(self, select=None):
        mats = core.all_materials()
        names = sorted(mats.keys())
        self.list.setRowCount(len(names))
        for i, n in enumerate(names):
            self.list.setItem(i, 0, QTableWidgetItem(n))
        if select in names:
            self.list.selectRow(names.index(select))

    def _load_selected(self):
        it = self.list.currentItem()
        if not it:
            return
        name = it.text()
        m = core.all_materials().get(name, {})
        self.f_name.set_value(name)
        for key, f in self.fields.items():
            v = m.get(key)
            f.set_value("" if v is None else v)

    def _save(self):
        name = self.f_name.text().strip()
        if not name:
            QMessageBox.warning(self, "", "Укажите название материала")
            return
        user = core.load_user_materials()
        rec = {}
        for key, f in self.fields.items():
            try:
                rec[key] = float(f.text().replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "", "Неверное число в поле «%s»" % key)
                return
        user[name] = rec
        core.save_user_materials(user)
        self._reload(select=name)

    def _delete(self):
        it = self.list.currentItem()
        if not it:
            return
        name = it.text()
        user = core.load_user_materials()
        if name not in user:
            QMessageBox.information(self, "", "Встроенные материалы удалить нельзя")
            return
        del user[name]
        core.save_user_materials(user)
        self._reload()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(core.APP_NAME)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
