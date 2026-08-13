# -*- coding: utf-8 -*-
"""
AFSD Predictor — интерфейс на PySide6.

Расчёты берутся из afsd_core (тот же модуль, что и у прежнего Tk-окна),
оформление — из afsd_theme. Здесь только представление: ни одной формулы.

Запуск:  python afsd_qt.py
"""

import sys
import math

import numpy as np

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox,
    QTabWidget, QSplitter, QFrame, QScrollArea, QSizePolicy, QStatusBar,
    QButtonGroup, QMessageBox,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

import afsd_core as core
from afsd_theme import THEMES, qss, mpl_rc, SP_M, SP_L, SP_XL


# ---------------------------------------------------------------------------
#  мелкие строительные блоки
# ---------------------------------------------------------------------------
class Card(QFrame):
    """Панель-карточка с заголовком и вертикальной раскладкой внутри."""

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SP_L, SP_L, SP_L, SP_L)
        outer.setSpacing(SP_M)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("CardTitle")
            outer.addWidget(lbl)
            self._title = lbl
        else:
            self._title = None
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

    def __init__(self, label, value="", unit="", width=96, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        # вертикальные поля строки — иначе соседние строки наезжают друг на
        # друга: QLineEdit со своей min-height выше, чем интервал по умолчанию
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
        # строка не должна сжиматься ниже собственной высоты. Высота задаётся
        # явно, а не через QSS: min-height из таблицы стилей не попадает в
        # sizeHint(), поэтому layout выделяет строке слишком мало места и
        # последняя в карточке подрезается.
        h = self.fontMetrics().height() + 14
        self.edit.setMinimumHeight(h)
        self.setMinimumHeight(h + 4)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def value(self, default=0.0):
        """Число из поля. Запятая допускается как десятичный разделитель."""
        try:
            return float(self.edit.text().strip().replace(",", "."))
        except ValueError:
            return default

    def set_value(self, v):
        self.edit.setText("%g" % v)


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

    def apply_palette(self, pal):
        """Перекрасить фигуру под тему и перерисовать."""
        matplotlib.rcParams.update(mpl_rc(pal))
        self.fig.set_facecolor(pal.plot_bg)
        for ax in self.fig.get_axes():
            ax.set_facecolor(pal.plot_axes)
            for spine in ax.spines.values():
                spine.set_edgecolor(pal.border)
            ax.tick_params(colors=pal.text_dim)
            ax.xaxis.label.set_color(pal.text)
            ax.yaxis.label.set_color(pal.text)
            ax.title.set_color(pal.text)
        self.canvas.draw_idle()


# ---------------------------------------------------------------------------
#  главное окно
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.lang = "en"
        self.theme_name = "dark"
        self.materials = core.all_materials()

        self.setWindowTitle(core.APP_NAME)
        self.resize(1500, 940)
        self.setMinimumSize(1180, 760)
        try:
            self.setWindowIcon(QIcon(core._bundled_file("app.ico")))
        except Exception:
            pass

        self._build_menu()
        self._build_ui()
        self._build_statusbar()
        self.apply_theme(self.theme_name)

    # ---------- перевод ----------
    def t(self, key):
        """Строка перевода из ядра; при отсутствии — сам ключ."""
        if self.lang == "zh" and key in core.ZH:
            return core.ZH[key]
        d = core.TR.get(key)
        if not d:
            return key
        return d.get(self.lang) or d.get("en") or key

    # ---------- меню ----------
    def _build_menu(self):
        mb = self.menuBar()

        m_file = mb.addMenu(self.t("menu_file"))
        for key, slot, seq in [
            ("menu_new", self.on_new, QKeySequence.New),
            ("menu_open", self.on_open, QKeySequence.Open),
            ("menu_save", self.on_save, QKeySequence.Save),
            ("menu_saveas", self.on_save_as, QKeySequence.SaveAs),
        ]:
            act = QAction(self.t(key), self)
            act.setShortcut(seq)
            act.triggered.connect(slot)
            m_file.addAction(act)
        m_file.addSeparator()
        act_quit = QAction(self.t("menu_exit"), self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_view = mb.addMenu(self.t("menu_settings"))
        self.act_theme = QAction(self.t("menu_theme") if "menu_theme" in core.TR
                                 else "Тёмная тема", self)
        self.act_theme.setCheckable(True)
        self.act_theme.setChecked(True)
        self.act_theme.setShortcut("Ctrl+T")
        self.act_theme.triggered.connect(
            lambda on: self.apply_theme("dark" if on else "light"))
        m_view.addAction(self.act_theme)

        m_lang = m_view.addMenu(self.t("menu_lang"))
        grp = QButtonGroup(self)
        for code, name in core.LANGS:
            a = QAction(name, self, checkable=True)
            a.setChecked(code == self.lang)
            a.triggered.connect(lambda _c, cc=code: self.set_language(cc))
            m_lang.addAction(a)

        m_help = mb.addMenu(self.t("menu_help"))
        a_guide = QAction(self.t("menu_guide"), self)
        a_guide.setShortcut("F1")
        a_guide.triggered.connect(self.on_guide)
        m_help.addAction(a_guide)
        a_about = QAction(self.t("menu_about"), self)
        a_about.triggered.connect(self.on_about)
        m_help.addAction(a_about)

    # ---------- каркас ----------
    def _build_ui(self):
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(1)

        # --- левая колонка: ввод, с прокруткой ---
        left_host = QWidget()
        left = QVBoxLayout(left_host)
        left.setContentsMargins(SP_L, SP_L, SP_M, SP_L)
        left.setSpacing(SP_L)
        left.addWidget(self._card_material())
        left.addWidget(self._card_process())
        left.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(left_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(340)
        scroll.setMaximumWidth(460)

        # --- правая часть: график + результат ---
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(SP_M, SP_L, SP_L, SP_L)
        rl.setSpacing(SP_L)

        self.tabs = QTabWidget()
        self.plot = PlotPane()
        self.tabs.addTab(self.plot, self.t("tab_plot") if "tab_plot" in core.TR else "Карта")
        rl.addWidget(self.tabs, 1)
        rl.addWidget(self._card_result())

        split.addWidget(scroll)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([380, 1120])
        self.setCentralWidget(split)

    def _card_material(self):
        card = Card(self.t("grp_material") if "grp_material" in core.TR else "Материал")
        self.cb_material = QComboBox()
        self.cb_material.addItems(sorted(self.materials.keys()))
        if core.DEFAULT_PRESET in self.materials:
            self.cb_material.setCurrentText(core.DEFAULT_PRESET)
        self.cb_material.currentTextChanged.connect(self._on_material)
        card.body.addWidget(self.cb_material)

        self.f_tsol = Field("T solidus", 582.0, "°C")
        self.f_t0 = Field("T₀", 25.0, "°C")
        card.body.addWidget(self.f_tsol)
        card.body.addWidget(self.f_t0)
        return card

    def _card_process(self):
        card = Card(self.t("grp_process") if "grp_process" in core.TR else "Режим")
        self.f_omega = Field("ω", 600.0, "об/мин")
        self.f_R = Field("R", 6.0, "мм")
        self.f_H = Field("H", 2.0, "мм")
        self.f_F = Field("F", 8.0, "кН")
        self.f_mu = Field("μ", 0.5, "")
        for f in (self.f_omega, self.f_R, self.f_H, self.f_F, self.f_mu):
            card.body.addWidget(f)

        btns = QHBoxLayout()
        btns.setSpacing(SP_M)
        self.btn_calc = QPushButton(self.t("btn_point") if "btn_point" in core.TR
                                    else "Рассчитать точку")
        self.btn_calc.setObjectName("Accent")
        self.btn_calc.clicked.connect(self.on_calc_point)
        btns.addWidget(self.btn_calc, 1)
        card.body.addLayout(btns)
        return card

    def _card_result(self):
        card = Card()
        self.lbl_result = QLabel("—")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # результат выводится увеличенным кеглем через rich text; QLabel считает
        # высоту по шрифту виджета, а не по разметке, поэтому задаём минимум сами
        self.lbl_result.setMinimumHeight(58)
        self.lbl_result.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("Hint")
        self.lbl_hint.setWordWrap(True)
        card.body.addWidget(self.lbl_result)
        card.body.addWidget(self.lbl_hint)
        return card

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage(core.APP_NAME)

    # ---------- тема ----------
    def apply_theme(self, name):
        self.theme_name = name
        pal = THEMES[name]
        self.pal = pal
        app = QApplication.instance()
        app.setStyleSheet(qss(pal))
        self.plot.apply_palette(pal)
        if hasattr(self, "act_theme"):
            self.act_theme.setChecked(name == "dark")

    def set_language(self, code):
        self.lang = code
        self.statusBar().showMessage(code)

    # ---------- расчёт ----------
    def _params(self):
        """Параметры для решателя из полей ввода."""
        name = self.cb_material.currentText()
        p = dict(self.materials.get(name, core.PRESETS[core.DEFAULT_PRESET]))
        p["T_solidus"] = self.f_tsol.value(p.get("T_solidus", 580.0))
        p["T0"] = self.f_t0.value(p.get("T0", 25.0))
        p["F"] = self.f_F.value(8.0) * 1e3          # кН -> Н
        p["mu"] = self.f_mu.value(0.5)
        p["eta"] = 1.0
        p["C_emp"] = None
        return p

    def on_calc_point(self):
        p = self._params()
        try:
            T, aud = core.compute_T_audit(self.f_omega.value(600.0),
                                          self.f_R.value(6.0),
                                          self.f_H.value(2.0), p)
        except Exception as exc:
            QMessageBox.critical(self, self.t("err"), str(exc))
            return
        Ts_K = core.c_to_k(p["T_solidus"])
        lo, hi = 0.6 * Ts_K - 273.15, 0.9 * Ts_K - 273.15
        inside = lo <= T <= hi
        col = self.pal.ok if inside else self.pal.danger
        self.lbl_result.setText(
            f'<span style="font-size:15pt;font-weight:600">T_peak = {T:.1f} °C</span>'
            f'<span style="color:{self.pal.text_dim}">  ({core.c_to_k(T):.1f} K)</span>'
            f'<br><span style="color:{col}">'
            f'{"в окне" if inside else "вне окна"} {lo:.0f}…{hi:.0f} °C</span>')
        self.lbl_hint.setText(
            f"режим: {aud['branch']}   τ_c={aud['tau_c']:.1f} МПа   "
            f"p={aud['p_contact']:.1f} МПа   μ_эфф={aud['mu_eff']:.3f}   "
            f"Q={aud['Q']:.0f} Вт")
        self._draw_demo(T, lo, hi)

    def _draw_demo(self, T, lo, hi):
        """Карта T_peak(ω, R) при текущих H, F, μ."""
        p = self._params()
        w = np.linspace(200, 1400, 60)
        R = np.linspace(3, 12, 60)
        W, RR = np.meshgrid(w, R)
        try:
            Z = core.solve_Tpeak(W, RR, self.f_H.value(2.0), p)
        except Exception as exc:
            self.statusBar().showMessage("ошибка расчёта карты: %s" % exc)
            return
        pal = self.pal
        self.plot.fig.clf()
        ax = self.plot.fig.add_subplot(111)
        cs = ax.contourf(W, RR, Z, levels=24, cmap="magma")
        ax.contour(W, RR, Z, levels=[lo, hi], colors=[pal.accent, pal.danger],
                   linewidths=1.6, linestyles="--")
        cb = self.plot.fig.colorbar(cs, ax=ax, pad=0.02)
        cb.set_label("T_peak, °C", color=pal.text)
        cb.ax.yaxis.set_tick_params(color=pal.text_dim)
        for t in cb.ax.get_yticklabels():
            t.set_color(pal.text_dim)
        ax.set_xlabel("ω, об/мин")
        ax.set_ylabel("R, мм")
        ax.plot(self.f_omega.value(600.0), self.f_R.value(6.0), "o",
                ms=9, mfc=pal.accent, mec=pal.accent_text, mew=1.4, zorder=5)
        self.plot.fig.tight_layout()
        self.plot.apply_palette(pal)

    def _on_material(self, name):
        m = self.materials.get(name)
        if not m:
            return
        self.f_tsol.set_value(m.get("T_solidus", 580.0))
        self.f_t0.set_value(m.get("T0", 25.0))

    # ---------- заглушки пунктов меню ----------
    def on_new(self):
        self.statusBar().showMessage("новый проект — в разработке")

    def on_open(self):
        self.statusBar().showMessage("открыть — в разработке")

    def on_save(self):
        self.statusBar().showMessage("сохранить — в разработке")

    def on_save_as(self):
        self.statusBar().showMessage("сохранить как — в разработке")

    def on_guide(self):
        txt = core.GUIDE_TEXT.get(self.lang) or core.GUIDE_TEXT.get("en", "")
        QMessageBox.information(self, self.t("menu_guide"), txt[:2000])

    def on_about(self):
        txt = core.ABOUT_TEXT.get(self.lang) or core.ABOUT_TEXT.get("en", "")
        QMessageBox.about(self, self.t("menu_about"), txt)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(core.APP_NAME)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
