# -*- coding: utf-8 -*-
"""
AFSD Predictor — отрисовка карт режимов.

Журнальное оформление рисунка живёт здесь, а не в коде окна: Tk- и
Qt-интерфейсы вызывают одни и те же функции, поэтому рисунок в обоих
одинаков и пригоден для вставки в статью без правок.

Оформление подобрано под требования журналов: гарнитура Times New Roman,
формулы через mathtext/STIX, палочки внутрь на всех четырёх сторонах,
чёрные изотермы с подписями, границы технологического окна пунктиром,
рамка с фиксированными параметрами в поле графика.

Модуль не зависит от GUI: сюда передают готовые массивы и настройки,
он рисует на переданной фигуре matplotlib.
"""

import math

import numpy as np
import matplotlib
import matplotlib.patheffects as mpe

import afsd_core as core

TNR = "Times New Roman"


class PlotStyle:
    """Настройки оформления рисунка.

    Значения по умолчанию — те, что подобраны для статьи; интерфейс меняет
    их через свои панели, но набор и смысл полей общий для обоих окон.
    """

    def __init__(self, **kw):
        self.fs = 13               # базовый кегль
        self.nlev = 24             # число градаций заливки
        self.window_only = False   # заливать только технологическое окно
        self.winfill = False       # зелёная подсветка окна
        self.lblpad = 6            # отступ названий осей
        self.tickpad = 3           # отступ цифр от осей
        self.cbar_pad = 0.06       # положение цветовой шкалы (подобрано для статьи)
        self.cbar_lblx = 3.5       # позиция надписи шкалы по X
        self.cbar_flip = False     # надпись шкалы на 180°
        self.annotx = 0.97         # положение рамки фикс-параметров
        self.annoty = 0.96
        self.annotscale = 1.0      # масштаб текста рамки
        self.aspect = 0.75         # высота/ширина бокса осей
        self.toolrad = False       # ось D показывать как радиус
        self.wlo, self.whi = 0.6, 0.9   # доли технологического окна
        self.elev, self.azim = 28, -130  # ракурс 3D
        self.n3d = 48              # плотность 3D-сетки
        self.reg_text = None       # уравнение под картой (или None)
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)


def plot_label(name, toolrad=False):
    """Подпись оси в журнальном стиле: «Rotational Speed, ω (rev/min)»."""
    n, sym, u = core.JLAB[name]
    if name == "D" and toolrad:                 # радиус вместо диаметра
        n, sym = "Tool Radius", "R"
    return r"%s, $%s$ (%s)" % (n, sym, u)


def plot_annot(name, val, toolrad=False):
    """Строка рамки фиксированных параметров: «Tool Diameter, D = 15 mm»."""
    n, sym, u = core.JLAB[name]
    if name == "D" and toolrad:
        n, sym, val = "Tool Radius", "R", val / 2.0
    return r"%s, $%s$ = %g %s" % (n, sym, val, u)


def annot_text(fixed, toolrad=False):
    """Многострочная рамка по словарю удерживаемых параметров."""
    return "\n".join(plot_annot(s, v, toolrad) for s, v in fixed.items())


def draw_2d(fig, X, Y, T, xN, yN, Tmin, Tmax, annot="", st=None, points=None):
    """Контурная карта T_peak — журнальное оформление.

    fig    — фигура matplotlib (очищается вызывающей стороной);
    X,Y,T  — сетка и температуры, °C;
    xN,yN  — символы параметров осей;
    Tmin/Tmax — границы технологического окна, °C;
    annot  — текст рамки фиксированных параметров;
    points — [{label, vals, T}] для маркеров.
    """
    st = st or PlotStyle()
    fs = st.fs
    matplotlib.rcParams["mathtext.fontset"] = "stix"    # Times-подобные формулы
    ax = fig.add_subplot(111)
    nlev = max(4, int(st.nlev))

    if st.window_only:
        cmap = matplotlib.colormaps["turbo"].with_extremes(under="white", over="white")
        levels = np.linspace(Tmin, Tmax, nlev)
        cf = ax.contourf(X, Y, T, levels=levels, cmap=cmap, extend="both")
    else:
        cf = ax.contourf(X, Y, T, levels=nlev, cmap="turbo")

    cb = fig.colorbar(cf, ax=ax, pad=st.cbar_pad)
    cb.set_label(r"Peak Temperature, $T$ ($^{\circ}$C)", fontsize=fs, fontname=TNR,
                 color="k", rotation=(270 if st.cbar_flip else 90))
    cb.ax.yaxis.set_label_coords(st.cbar_lblx, 0.5)
    cb.ax.tick_params(labelsize=fs - 1, colors="k")
    for lab in cb.ax.get_yticklabels():
        lab.set_fontname(TNR)

    stroke = [mpe.withStroke(linewidth=2.4, foreground="white")]
    # изотермы — тонкие чёрные линии с подписями (Times, без обводки)
    cs = ax.contour(X, Y, T, levels=10, colors="k", linewidths=0.5, alpha=0.6)
    for t in ax.clabel(cs, inline=True, fontsize=max(6, fs - 2), fmt="%.0f", colors="k"):
        t.set_fontname(TNR)

    # зелёная подсветка окна — по желанию: иначе цвет остаётся чистым
    # градиентом без резкого перехода
    if (not st.window_only and st.winfill
            and np.nanmax(T) >= Tmin and np.nanmin(T) <= Tmax):
        mask = np.where((T >= Tmin) & (T <= Tmax), 1.0, np.nan)
        ax.contourf(X, Y, mask, levels=[0.5, 1.5], colors=["#19d219"], alpha=0.30)

    # Гомологическая температура T/T_s — отношение АБСОЛЮТНЫХ температур,
    # поэтому безразмерна. В скобках — значение в °C, чтобы границу можно
    # было читать прямо с карты (шкала и изотермы тоже в °C).
    for lev, col, tag in [(Tmin, "#1565ff", r"$T/T_{s} = %g$" % st.wlo),
                          (Tmax, "#e8112d", r"$T/T_{s} = %g$" % st.whi)]:
        try:
            c = ax.contour(X, Y, T, levels=[lev], colors=col, linewidths=2.0,
                           linestyles="--")
            for t in ax.clabel(c, fmt={lev: "%s (%.0f)" % (tag, lev)},
                               fontsize=max(6, fs - 1), colors="k"):
                t.set_fontname(TNR)
                t.set_path_effects(stroke)
        except Exception:
            pass

    draw_points(ax, xN, yN, fs, points)

    if annot:
        ha = "right" if st.annotx >= 0.5 else "left"
        va = "top" if st.annoty >= 0.5 else "bottom"
        afs = max(4.0, fs * st.annotscale)
        ax.text(st.annotx, st.annoty, annot, transform=ax.transAxes, ha=ha, va=va,
                fontsize=afs, fontname=TNR, color="k", zorder=50,
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="0.5", alpha=1.0))

    ax.set_xlabel(plot_label(xN, st.toolrad), fontsize=fs, fontname=TNR,
                  color="k", labelpad=st.lblpad)
    ax.set_ylabel(plot_label(yN, st.toolrad), fontsize=fs, fontname=TNR,
                  color="k", labelpad=st.lblpad)
    # палочки внутрь на всех четырёх сторонах, цифры — только низ/лево
    ax.tick_params(direction="in", labelsize=fs - 1, colors="k", pad=st.tickpad,
                   top=True, right=True, labeltop=False, labelright=False)
    ax.tick_params(which="minor", direction="in", top=True, right=True,
                   labeltop=False, labelright=False)

    if st.toolrad:                       # ось диаметра в радиусах (R = D/2)
        from matplotlib.ticker import FuncFormatter
        half = FuncFormatter(lambda v, _p: ("%g" % (v / 2.0)))
        if xN == "D":
            ax.xaxis.set_major_formatter(half)
        if yN == "D":
            ax.yaxis.set_major_formatter(half)

    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_fontname(TNR)
        lab.set_color("k")

    if st.aspect > 0.05:
        try:
            ax.set_box_aspect(st.aspect)
        except Exception:
            pass

    overlay_regression(fig, fs, st.reg_text)
    return ax


def draw_3d(fig, X, Y, T, xN, yN, Tmin, Tmax, annot="", st=None):
    """Поверхность T_peak с плоскостями границ технологического окна."""
    st = st or PlotStyle()
    fs = st.fs
    matplotlib.rcParams["mathtext.fontset"] = "stix"
    ax = fig.add_subplot(111, projection="3d")
    rc = max(8, int(st.n3d))

    if st.window_only:
        from matplotlib.colors import Normalize
        cmap = matplotlib.colormaps["turbo"].with_extremes(under="white", over="white")
        surf = ax.plot_surface(X, Y, T, cmap=cmap, norm=Normalize(Tmin, Tmax, clip=False),
                               linewidth=0, antialiased=False, alpha=1.0,
                               rcount=rc, ccount=rc)
    else:
        surf = ax.plot_surface(X, Y, T, cmap="turbo", linewidth=0,
                               antialiased=False, alpha=1.0, rcount=rc, ccount=rc)

    cb = fig.colorbar(surf, ax=ax, pad=st.cbar_pad + 0.04, shrink=0.6)
    cb.set_label(r"Peak Temperature, $T$ ($^{\circ}$C)", fontsize=fs, fontname=TNR,
                 color="k", rotation=(270 if st.cbar_flip else 90))
    cb.ax.yaxis.set_label_coords(st.cbar_lblx, 0.5)
    cb.ax.tick_params(labelsize=fs - 1, colors="k")
    for lab in cb.ax.get_yticklabels():
        lab.set_fontname(TNR)

    # полупрозрачные плоскости границ окна — видно, какая часть поверхности в допуске
    xp = np.array([[X.min(), X.max()], [X.min(), X.max()]])
    yp = np.array([[Y.min(), Y.min()], [Y.max(), Y.max()]])
    if T.min() <= Tmin <= T.max():
        ax.plot_surface(xp, yp, np.full_like(xp, Tmin), color="#1565ff", alpha=0.18)
    if T.min() <= Tmax <= T.max():
        ax.plot_surface(xp, yp, np.full_like(xp, Tmax), color="#e8112d", alpha=0.18)

    ax.set_xlabel(plot_label(xN, st.toolrad), fontsize=fs - 1, fontname=TNR, color="k")
    ax.set_ylabel(plot_label(yN, st.toolrad), fontsize=fs - 1, fontname=TNR, color="k")
    ax.set_zlabel(r"Peak Temperature, $T$ ($^{\circ}$C)", fontsize=fs - 1,
                  fontname=TNR, color="k")
    ax.tick_params(labelsize=fs - 2, colors="k")

    if st.toolrad:
        from matplotlib.ticker import FuncFormatter
        half = FuncFormatter(lambda v, _p: ("%g" % (v / 2.0)))
        if xN == "D":
            ax.xaxis.set_major_formatter(half)
        if yN == "D":
            ax.yaxis.set_major_formatter(half)

    for lab in (ax.get_xticklabels() + ax.get_yticklabels() + ax.get_zticklabels()):
        lab.set_fontname(TNR)
        lab.set_color("k")

    if annot:
        ha = "right" if st.annotx >= 0.5 else "left"
        va = "top" if st.annoty >= 0.5 else "bottom"
        afs = max(4.0, fs * st.annotscale)
        ax.text2D(st.annotx, st.annoty, annot, transform=ax.transAxes, ha=ha, va=va,
                  fontsize=afs, fontname=TNR, color="k")

    ax.view_init(elev=int(st.elev), azim=int(st.azim))
    if st.reg_text:
        fig.text(0.5, 0.015, st.reg_text, ha="center", va="bottom",
                 fontsize=max(7, fs - 2), family=TNR, color="#111",
                 bbox=dict(boxstyle="round,pad=0.3", fc="#f6f6f6", ec="0.6"))
    return ax


def draw_points(ax, xN, yN, fs, points):
    """Маркер + рамка с буквой и пиковой T; подпись отражается у правого края."""
    if not points:
        return
    x0, x1 = ax.get_xlim()
    for p in points:
        vals = p.get("vals", {})
        if xN not in vals or yN not in vals:
            continue
        px, py = vals[xN], vals[yN]
        ax.plot(px, py, "o", ms=8, mfc="white", mec="k", mew=1.5, zorder=40)
        near_right = (px - x0) > 0.82 * (x1 - x0) if x1 > x0 else False
        ax.annotate("%s  %.0f" % (p.get("label", "?"), p.get("T", float("nan"))),
                    (px, py), textcoords="offset pixels",
                    xytext=(-13, 0) if near_right else (13, 0),
                    ha="right" if near_right else "left", va="center",
                    fontsize=fs, fontweight="bold", fontname=TNR, color="k",
                    zorder=41, bbox=dict(boxstyle="round,pad=0.25", fc="white",
                                         ec="0.4", alpha=0.95))


def overlay_regression(fig, fs, text):
    """Сокращённое уравнение T_peak(x,y) внизу карты — по тумблеру."""
    fig.tight_layout(rect=(0, 0.08, 1, 1) if text else (0, 0, 1, 1))
    if text:
        fig.text(0.5, 0.015, text, ha="center", va="bottom",
                 fontsize=max(7, fs - 2), family=TNR, color="#111",
                 bbox=dict(boxstyle="round,pad=0.3", fc="#f6f6f6", ec="0.6"))
