# -*- coding: utf-8 -*-
"""
AFSD Process Window Calculator (v3)
===================================
Оконный калькулятор пиковой температуры, 2D-карт и 3D-поверхностей режимов
процесса Additive Friction Stir Deposition (AFSD).

Модель (статья Y. Dvirnyk et al., Next Materials 11 (2026) 101778):
  sigma_y(T) = sigma_ref * [1 - ((T - T0)/(T_ref - T0))^m]      (ур. 13/14)
  tau_y      = sigma_y / sqrt(3)                                 (Мизес)
  Q_total    = (2/3) * pi * omega * tau_y * (R^3 + 3 R^2 H)      (ур. 4)
  T_peak     = T0 + Q_total / (4 k R)                            (ур. 10)
T_peak — самосогласованная итерация. Окно: 0.6 Ts <= T_peak <= 0.9 Ts (ур. 11)

v3: меню Файл/Настройки/Справка, проекты (JSON), языки UK/RU/EN, настройки
    шрифтов программы и графика, подвижный разделитель, расширенная БД сплавов.
"""

import os
import sys
import json
import math
import itertools
import numpy as np
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog, simpledialog

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
import matplotlib.patheffects as mpe
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


# ---------------------------------------------------------------------------
#  Расчётное ядро вынесено в afsd_core.py (физика, материалы, переводы).
#  Имена импортируются в этот модуль, поэтому GUI-код ниже не менялся.
# ---------------------------------------------------------------------------
from afsd_core import *            # noqa: F401,F403
# приватные имена (с подчёркиванием) через «import *» не переносятся — явно:
from afsd_core import (_app_dir, _user_file, _bundled_file,      # noqa: F401
                       _load_json_db, _save_json_db, _vbisect)
import afsd_core as _core

# ----------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # настройки внешнего вида
        self.lang = "en"                 # базовый язык — английский
        self.ui_family = "Segoe UI"
        self.ui_size = 10
        self.plot_family = "DejaVu Sans"
        self.plot_fs = 13               # крупнее по умолчанию — читаемо «как для статьи»
        self.cbar_pad = 0.06          # отступ цветовой шкалы от графика
        self.n3d = 48                 # плотность 3D-сетки (меньше = быстрее вращение)

        self._init_vars()
        self.geometry("1400x900")
        self.minsize(1120, 740)
        try:                                   # иконка окна (рядом со скриптом / в .exe)
            self.iconbitmap(_bundled_file("app.ico"))
        except Exception:
            pass
        self._apply_fonts()
        self._build_menu()
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)
        self._build_body(self.body)
        self._update_title()
        self.protocol("WM_DELETE_WINDOW", self._on_close)   # запрос сохранения при закрытии
        self.after(150, self.build)
        self.after(300, self._mark_saved)                   # снимок чистого состояния

    # ---------- i18n ----------
    def t(self, key):
        d = TR.get(key, {})
        if self.lang == "zh":
            return ZH.get(key) or d.get("en") or key   # китайский: словарь ZH, иначе англ.
        return d.get(self.lang) or d.get("en") or key   # фолбэк на английский

    def _model_label(self, key):
        return self.t("model_" + key)

    def _model_from_label(self, label):
        for k in MODEL_ORDER:
            if self._model_label(k) == label:
                return k
        return "phys"

    # ---------- persistent state ----------
    def _init_vars(self):
        self.materials = all_materials()
        self.mu_tables = all_mu_tables()      # таблицы μ(T): встроенные + пользовательские
        pr = PRESETS[DEFAULT_PRESET]
        self._fields = {}
        for key in ("sigma_ref", "T_ref", "m", "k", "T_solidus", "T0"):
            self._fields[key] = tk.StringVar(value=str(pr[key]))
        self._fields["C_emp"] = tk.StringVar(value="" if pr["C_emp"] is None else str(pr["C_emp"]))
        self._fields["eta"] = tk.StringVar(value="1.0")
        self._fields["rod_L"] = tk.StringVar(value="0")    # вылет прутка [мм]; 0 = сток в патрон выключен
        self._fields["F"] = tk.StringVar(value="8.0")      # осевая сила [кН]
        self._fields["mu"] = tk.StringVar(value="0.5")     # коэф. трения контактной пары
        # режим каждого параметра: "range" (диапазон, в матрицу/оси) или "fixed" (одно число).
        # По умолчанию варьируем только ω и v_t — компактная матрица 3²; остальное фиксировано.
        self.vary = {s: tk.StringVar(value=("range" if s in ("ω", "vx") else "fixed"))
                     for s in ("ω", "vz", "vx", "D", "H", "a", "F")}
        self.mu_tdep_var = tk.BooleanVar(value=False)       # μ температурозависимый
        self.mu_pair_var = tk.StringVar(value=MU_PAIR_NONE)  # таблица μ(T) для пары
        self.use_feedsink_var = tk.BooleanVar(value=True)   # адвективный сток подачи (ρcp·V̇)
        self._fields["rho"] = tk.StringVar(value=str(pr.get("rho", 2700.0)))
        self._fields["cp"] = tk.StringVar(value=str(pr.get("cp", 900.0)))
        # подложка (для кондукции 4kR и числа Пекле)
        self._fields["k_sub"] = tk.StringVar(value=str(pr["k"]))
        self._fields["rho_sub"] = tk.StringVar(value=str(pr.get("rho", 2700.0)))
        self._fields["cp_sub"] = tk.StringVar(value=str(pr.get("cp", 900.0)))
        # подложка: копирует материал прутка (True) или своя (False) + выбранный материал
        self.sub_same_var = tk.BooleanVar(value=True)
        self.substrate_var = tk.StringVar(value=DEFAULT_PRESET)
        # шайба (плечо) для режима shouldered: материал + k (отвод тепла вверх)
        self.shoe_var = tk.StringVar(value=SHOE_NONE)
        self.bore_var = tk.BooleanVar(value=False)   # кольцевой контакт плеча
        self._fields["k_shoe"] = tk.StringVar(value="25")
        self._fields["v_dep"] = tk.StringVar(value="5.0")
        self.use_pe_var = tk.BooleanVar(value=False)
        self.beadw_on_var = tk.BooleanVar(value=False)   # учитывать свою ширину валика (только в точке)
        self.tdep_var = tk.BooleanVar(value=False)
        self.input_mode = "kin"           # "kin" (shoulderless) | "shoulder" (MELD)
        self.input_mode_var = tk.StringVar(value="kin")
        self.model_key = "phys"
        defs = dict(w_min=200.0, w_max=1000.0, R_min=2.5, R_max=7.5, H_min=0.5, H_max=4.0,
                    pt_w=500.0, pt_R=5.0, pt_H=2.0,
                    vz_min=0.5, vz_max=3.0, vx_min=1.0, vx_max=10.0,
                    D_min=10.0, D_max=20.0, w_bead=12.0, pt_vz=1.5, pt_vx=5.0, pt_D=15.0,
                    a_min=7.0, a_max=12.0, pt_a=9.5, R_shoe=19.0,
                    F_min=4.0, F_max=20.0, pt_F=8.0,
                    # геометрия 3D-схемы (мм)
                    sub_L=52.0, sub_W=32.0, sub_t=6.0, trail_len=26.0,
                    rod_len=20.0, shoe_th=9.0, bar_len=16.0)
        for key, val in defs.items():
            self._fields[key] = tk.StringVar(value=str(val))
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        self.model_key = "phys"           # оба процесса используют физ. модель
        self.view_var = tk.StringVar(value="2D")
        self.colormode_var = tk.StringVar(value="full")
        # оси и фиксированные значения (2 оси + остальные фикс.)
        self.xaxis_var = tk.StringVar(value="ω")
        self.yaxis_var = tk.StringVar(value="vx")
        # рабочее (удерживаемое) значение каждого параметра: для «fixed» — константа,
        # для «range»-не-оси — срез (слайдер). Старт — из значений точки pt_*.
        _fixdef = {"ω": 500.0, "R": 5.0, "H": 2.0, "vz": 1.5, "vx": 5.0,
                   "D": 15.0, "a": 9.5, "F": 8.0}
        self.fix_vars = {f: tk.DoubleVar(value=v) for f, v in _fixdef.items()}
        self.result_var = tk.StringVar(value="—")
        self.plotfs_var = tk.IntVar(value=self.plot_fs)   # размер текста графика
        self.lblpad_var = tk.IntVar(value=6)              # отступ названий осей
        self.tickpad_var = tk.IntVar(value=3)             # отступ цифр от осей
        self.nlev_var = tk.IntVar(value=24)               # число градиентных цветов
        self.aspect_var = tk.DoubleVar(value=0.75)        # аспект (высота/ширина) = H/W
        self.aspw_var = tk.DoubleVar(value=4.0)           # отношение сторон: ширина
        self.asph_var = tk.DoubleVar(value=3.0)           # отношение сторон: высота
        self.annotx_var = tk.DoubleVar(value=0.97)        # позиция рамки X (0..1)
        self.annoty_var = tk.DoubleVar(value=0.96)        # позиция рамки Y (0..1)
        self.toolrad_var = tk.BooleanVar(value=False)     # радиус вместо диаметра
        self.cbar_flip_var = tk.BooleanVar(value=False)   # надпись шкалы на 180°
        self.cbar_lblx_var = tk.DoubleVar(value=3.5)      # позиция надписи шкалы по X
        self.cbar_pad_var = tk.DoubleVar(value=self.cbar_pad)  # положение шкалы (отступ)
        self.annotscale_var = tk.DoubleVar(value=1.0)     # масштаб рамки фикс-параметров
        self.wlo_var = tk.DoubleVar(value=0.6)            # нижняя граница окна (×T_s)
        self.whi_var = tk.DoubleVar(value=0.9)            # верхняя граница окна (×T_s)
        self.winfill_var = tk.BooleanVar(value=False)     # зелёная подсветка окна (полный диапазон)
        self.showreg_var = tk.BooleanVar(value=False)     # сокр. регрессия T(x,y) на карте
        self.elev_var = tk.IntVar(value=28)               # 3D: угол подъёма
        self.azim_var = tk.IntVar(value=-130)             # 3D: азимут
        self.n3d_var = tk.IntVar(value=self.n3d)          # 3D: плотность сетки
        # раздельные значения оформления для 2D и 3D (всё, кроме температурного окна).
        # 3D-старт: меньше текст, ближе шкала — обычно так лучше выглядит.
        self._prev_view = "2D"
        self._style_store = {"2D": {}, "3D": {}}
        self._save_style("2D")
        self._save_style("3D")
        self._style_store["3D"]["plotfs"] = 11
        self._style_store["3D"]["annotx"] = 0.02
        self._style_store["3D"]["cbar_pad"] = 0.10
        self._style_collapsed = True                       # панель оформления свёрнута (экономит место)
        self._collapsed = {}              # состояние свёрнутости секций (по ключам)
        self._last_grid = None
        self._points = []                 # нанесённые точки: [{label, vals, T}]
        self._hover_idx = None            # точка под курсором (для крестика удаления)
        self._project_path = None         # путь текущего проекта (для «Сохранить»)

    # ---------- fonts ----------
    def _apply_fonts(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        # Надёжный способ: меняем именованные шрифты Tk — они применяются
        # ко всем виджетам (ttk, меню, диалоги) сразу и вживую.
        for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(fname).configure(family=self.ui_family, size=self.ui_size)
            except tk.TclError:
                pass
        f = (self.ui_family, self.ui_size)
        fb = (self.ui_family, self.ui_size, "bold")
        style.configure(".", font=f)
        style.configure("TLabelframe.Label", font=fb, foreground="#16407a")
        style.configure("TButton", font=f, padding=(8, 4))
        # современная палитра (светлая, не тёмная тема)
        style.configure("TNotebook.Tab", font=fb, padding=(14, 6))
        style.map("TNotebook.Tab", foreground=[("selected", "#16407a")])
        style.configure("Treeview.Heading", font=fb)
        style.configure("Treeview", rowheight=max(20, self.ui_size + 10))
        # акцентная кнопка «Построить» (оранжевая, заметная)
        style.configure("Accent.TButton", font=fb, foreground="white",
                        background="#e8730c", padding=(14, 6))
        style.map("Accent.TButton", background=[("active", "#cf6406"), ("pressed", "#b85705")])
        # кнопки тулбара по группам (цветные подложки)
        for nm, bg, ac in (("ToolNav", "#dbe7f5", "#c3d6ef"),
                           ("ToolView", "#e6dcf2", "#d6c6e8"),
                           ("ToolSave", "#dcefdc", "#c6e3c6")):
            style.configure(nm + ".TButton", font=(self.ui_family, self.ui_size + 1),
                            background=bg, padding=(5, 3), relief="flat")
            style.map(nm + ".TButton", background=[("active", ac)])
        self.option_add("*TCombobox*Listbox.font", f)
        self.option_add("*Menu.font", f)
        matplotlib.rcParams["font.family"] = self.plot_family
        matplotlib.rcParams["font.size"] = self.plot_fs

    # ---------- menu ----------
    def _update_title(self):
        base = self.t("title")
        if self._project_path:
            base += " — " + os.path.basename(self._project_path)
        self.title(base)

    def _build_menu(self):
        menubar = tk.Menu(self, font=(self.ui_family, self.ui_size))

        m_file = tk.Menu(menubar, tearoff=0, font=(self.ui_family, self.ui_size))
        m_file.add_command(label=self.t("menu_new"), command=self.new_project,
                           accelerator="Ctrl+N")
        m_file.add_command(label=self.t("menu_open"), command=self.open_project,
                           accelerator="Ctrl+O")
        m_file.add_separator()
        m_file.add_command(label=self.t("menu_save"), command=self.save_project,
                           accelerator="Ctrl+S")
        m_file.add_command(label=self.t("menu_save_as"), command=self.save_project_as,
                           accelerator="Ctrl+Shift+S")
        m_file.add_separator()
        m_file.add_command(label=self.t("menu_exit"), command=self._on_close)
        menubar.add_cascade(label=self.t("menu_file"), menu=m_file)

        # снимок / экспорт графика (рядом с настройками)
        m_exp = tk.Menu(menubar, tearoff=0, font=(self.ui_family, self.ui_size))
        m_exp.add_command(label=self.t("menu_png"), command=self.save_png,
                          accelerator="Ctrl+Shift+P")
        m_exp.add_command(label=self.t("menu_pdf"), command=self.save_pdf,
                          accelerator="Ctrl+Shift+D")
        m_exp.add_command(label=self.t("menu_svg"), command=self.save_svg,
                          accelerator="Ctrl+Shift+G")
        m_exp.add_separator()
        m_exp.add_command(label=self.t("menu_csv"), command=self.export_csv,
                          accelerator="Ctrl+Shift+E")
        menubar.add_cascade(label=self.t("menu_export"), menu=m_exp)

        m_set = tk.Menu(menubar, tearoff=0, font=(self.ui_family, self.ui_size))
        m_set.add_command(label=self.t("menu_settings_dlg"), command=self.open_settings)
        m_lang = tk.Menu(m_set, tearoff=0, font=(self.ui_family, self.ui_size))
        for code, name in LANGS:
            m_lang.add_radiobutton(label=name, value=code, variable=tk.StringVar(value=self.lang),
                                   command=lambda c=code: self.set_language(c))
        m_set.add_cascade(label=self.t("menu_language"), menu=m_lang)
        menubar.add_cascade(label=self.t("menu_settings"), menu=m_set)

        m_help = tk.Menu(menubar, tearoff=0, font=(self.ui_family, self.ui_size))
        m_help.add_command(label=self.t("menu_guide"), command=self.show_guide,
                           accelerator="F1")
        m_help.add_separator()
        m_help.add_command(label=self.t("menu_about"), command=self.show_about)
        menubar.add_cascade(label=self.t("menu_help"), menu=m_help)

        self.config(menu=menubar)
        self._bind_hotkeys()

    def _bind_hotkeys(self):
        """Стандартные горячие клавиши (на каждый метод).

        Привязка делается и к корню (bind_all), и к самому окну: matplotlib-канва
        и поля ввода могут перехватывать клавиши, и тогда bind_all в одиночку
        срабатывает не всегда. Каждый вызов защищён: исключение в обработчике
        не должно молча гасить остальные горячие клавиши."""
        binds = {
            "<F1>": self.show_guide,
            "<Control-n>": self.new_project, "<Control-N>": self.new_project,
            "<Control-o>": self.open_project, "<Control-O>": self.open_project,
            "<Control-s>": self.save_project, "<Control-S>": self.save_project,
            "<Control-Shift-s>": self.save_project_as, "<Control-Shift-S>": self.save_project_as,
            "<Control-Shift-p>": self.save_png, "<Control-Shift-P>": self.save_png,
            "<Control-Shift-d>": self.save_pdf, "<Control-Shift-D>": self.save_pdf,
            "<Control-Shift-g>": self.save_svg, "<Control-Shift-G>": self.save_svg,
            "<Control-Shift-e>": self.export_csv, "<Control-Shift-E>": self.export_csv,
        }
        def _wrap(f):
            def _h(event=None, _f=f):
                try:
                    _f()
                except Exception as exc:                 # не гасим остальные клавиши
                    print("[AFSD hotkey] %s failed: %r" % (getattr(_f, "__name__", _f), exc))
                return "break"
            return _h
        for seq, fn in binds.items():
            h = _wrap(fn)
            self.bind_all(seq, h)
            self.bind(seq, h)                            # дубль на само окно

    # ---------- body ----------
    def _section(self, parent, title, key):
        """Сворачиваемая секция в рамке: заголовок-бар [⊟/⊞] + тело. Возвращает тело."""
        outer = tk.Frame(parent, bd=1, relief="solid", background="#aab8cc")
        outer.pack(fill="x", pady=3, padx=2)
        hdr = tk.Label(outer, cursor="hand2", anchor="w", padx=6, pady=3,
                       font=(self.ui_family, self.ui_size, "bold"), fg="#16407a", bg="#e8eef7")
        hdr.pack(fill="x")
        body = ttk.Frame(outer, padding=(7, 3))
        if not self._collapsed.get(key, False):
            body.pack(fill="x")

        def settext():
            # ⊞ — свёрнуто (можно развернуть), ⊟ — развёрнуто (можно свернуть)
            hdr.config(text=("⊞  " if self._collapsed.get(key, False) else "⊟  ") + title)

        def toggle(_e=None):
            self._collapsed[key] = not self._collapsed.get(key, False)
            if self._collapsed[key]:
                body.pack_forget()
            else:
                body.pack(fill="x")
            settext()
            if getattr(self, "_left_canvas", None) is not None:
                self._left_canvas.update_idletasks()
                self._left_canvas.configure(scrollregion=self._left_canvas.bbox("all"))

        hdr.bind("<Button-1>", toggle)
        settext()
        return body

    # ---------- защита от случайной прокрутки значений и ввод с запятой ----------
    def _descendants(self, w):
        for c in w.winfo_children():
            yield c
            yield from self._descendants(c)

    @staticmethod
    def _comma_to_dot(event):
        """Ввод запятой в числовом поле -> точка (instance-level, до вставки классом)."""
        try:
            event.widget.insert("insert", ".")
        except tk.TclError:
            return None
        return "break"

    def _lock_wheel(self, parent, canvas=None):
        """Полировка ввода: колесо над Spinbox/Combobox/Scale НЕ меняет значение
           (если задан canvas — прокручивает его), а запятая в полях вводится как точка.
           Защита от случайного сбоя настроек и от ошибок десятичного разделителя."""
        def on_wheel(e):
            if canvas is not None and getattr(e, "delta", 0):
                canvas.yview_scroll(int(-e.delta / 120), "units")
            return "break"

        def on_b4(e):
            if canvas is not None:
                canvas.yview_scroll(-1, "units")
            return "break"

        def on_b5(e):
            if canvas is not None:
                canvas.yview_scroll(1, "units")
            return "break"
        for w in self._descendants(parent):
            cls = w.winfo_class()
            if cls in ("TSpinbox", "TCombobox", "TScale", "Spinbox", "Scale"):
                w.bind("<MouseWheel>", on_wheel, add="+")
                w.bind("<Button-4>", on_b4, add="+")
                w.bind("<Button-5>", on_b5, add="+")
            if cls in ("Entry", "TEntry", "Spinbox", "TSpinbox"):
                w.bind("<KeyPress-comma>", self._comma_to_dot, add="+")

    def _labeled(self, parent, key_tr, field_key, width=10):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=self.t(key_tr), width=30, anchor="w").pack(side="left")
        ent = ttk.Entry(row, textvariable=self._fields[field_key], width=width)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<Return>", self._on_param_edit)
        ent.bind("<FocusOut>", self._on_param_edit)

    def _on_param_edit(self, *_):
        """Любое изменение поля свойств/диапазона -> пересчёт формул и графиков."""
        self.build()

    def _on_textsize(self, *_):
        """Размер текста графика: перерисовка из кэша без пересчёта T (отзывчиво)."""
        try:
            self.plot_fs = int(round(float(self.plotfs_var.get())))
        except (ValueError, tk.TclError):
            return
        self._redraw_from_cache()

    def _aspect_value(self):
        """Аспект бокса (высота/ширина) из полей отношения W:H."""
        try:
            w, h = float(self.aspw_var.get()), float(self.asph_var.get())
            if w > 0 and h > 0:
                return h / w
        except (ValueError, tk.TclError):
            pass
        return 0.0

    def _on_aspect_ratio(self, *_):
        """Изменили отношение сторон (поля W:H или пресет) -> перерисовать."""
        self.aspect_var.set(round(self._aspect_value(), 4))
        self._on_textsize()

    def _set_aspect_preset(self, txt):
        try:
            w, h = txt.replace(" ", "").split(":")
            self.aspw_var.set(float(w)); self.asph_var.set(float(h))
        except (ValueError, AttributeError):
            return
        self._on_aspect_ratio()

    def _redraw_from_cache(self, idle=False):
        """Перерисовать график из кэша (без пересчёта T) — стиль, точки, наведение."""
        if self._last_grid is None:
            return
        xN, yN, xv, yv, T, fixed = self._last_grid
        X, Y = np.meshgrid(xv, yv)
        try:
            Tsol = self._f("T_solidus")
        except ValueError:
            return
        Tmin, Tmax = self._window_C(Tsol)
        annot = "\n".join(self._plot_annot(s, v) for s, v in fixed.items())
        self.fig.clf()
        if self.view_var.get() == "3D":
            self._draw_3d(X, Y, T, xN, yN, Tmin, Tmax, annot)
        else:
            self._draw_2d(X, Y, T, xN, yN, Tmin, Tmax, annot)
        (self.canvas.draw_idle if idle else self.canvas.draw)()

    def _on_mode_change(self):
        self.input_mode = self.input_mode_var.get()
        self.model_key = "phys"          # оба процесса — физическая модель
        self.xaxis_var.set("ω")
        self.yaxis_var.set("vx" if self.input_mode == "kin" else "vx")
        self._relayout()

    def _on_vary_change(self, sym):
        """Сменили режим параметра (диапазон/одно число) — пересобрать оси и UI."""
        # если параметр перестал быть осью — переназначить ось из оставшихся диапазонных
        order = self._order()
        if self.xaxis_var.get() not in order and order:
            self.xaxis_var.set(order[0])
        if self.yaxis_var.get() not in order or self.yaxis_var.get() == self.xaxis_var.get():
            alt = [s for s in order if s != self.xaxis_var.get()]
            if alt:
                self.yaxis_var.set(alt[0])
        self._relayout()

    def _build_body(self, parent):
        # подвижный разделитель
        self.paned = ttk.PanedWindow(parent, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(self.paned)
        right = ttk.Frame(self.paned)
        self.paned.add(left, weight=0)
        self.paned.add(right, weight=1)
        self.after(60, lambda: self._set_sash())

        self._build_inputs(left)
        self._build_right(right)

    def _set_sash(self):
        try:
            self.paned.sashpos(0, 390)
        except Exception:
            pass

    def _build_inputs(self, parent):
        # прокручиваемая левая колонка (контент может уходить за экран)
        canv = tk.Canvas(parent, highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canv.yview)
        canv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canv.pack(side="left", fill="both", expand=True)
        self._left_canvas = canv
        inner = ttk.Frame(canv)
        self._left_win = canv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canv.configure(scrollregion=canv.bbox("all")))
        canv.bind("<Configure>", lambda e: canv.itemconfigure(self._left_win, width=e.width))
        _wheel = lambda e: canv.yview_scroll(int(-e.delta / 120), "units")
        canv.bind("<Enter>", lambda e: canv.bind_all("<MouseWheel>", _wheel))
        canv.bind("<Leave>", lambda e: canv.unbind_all("<MouseWheel>"))

        g0 = self._section(inner, self.t("grp_alloy"), "alloy")
        cb = ttk.Combobox(g0, textvariable=self.preset_var, values=list(self.materials),
                          state="readonly")
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: self._load_preset())
        ttk.Button(g0, text=self.t("btn_addmat"), command=self.add_material).pack(
            fill="x", pady=(4, 0))

        gim = self._section(inner, self.t("grp_inmode"), "inmode")
        self.input_mode_var.set(self.input_mode)
        ttk.Radiobutton(gim, text=self.t("mode_kin"), value="kin", variable=self.input_mode_var,
                        command=self._on_mode_change).pack(anchor="w")
        ttk.Radiobutton(gim, text=self.t("mode_shoulder"), value="shoulder",
                        variable=self.input_mode_var, command=self._on_mode_change).pack(anchor="w")

        g1 = self._section(inner, self.t("grp_props_dep"), "props")
        for tr, key in [("lbl_sigma", "sigma_ref"), ("lbl_tref", "T_ref"), ("lbl_m", "m"),
                        ("lbl_k", "k"), ("lbl_tsol", "T_solidus"), ("lbl_t0", "T0"),
                        ("lbl_c", "C_emp"), ("lbl_eta", "eta"), ("lbl_rho", "rho"),
                        ("lbl_cp", "cp"), ("lbl_rodl", "rod_L")]:
            self._labeled(g1, tr, key)
        # коэффициент трения μ: явный переключатель «константа / таблица μ(T)»
        rowmm = ttk.Frame(g1); rowmm.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(rowmm, text=self.t("rb_muconst"), value=False, variable=self.mu_tdep_var,
                        command=self._on_mu_mode).pack(side="left")
        ttk.Radiobutton(rowmm, text=self.t("rb_mutab"), value=True, variable=self.mu_tdep_var,
                        command=self._on_mu_mode).pack(side="left", padx=(8, 0))
        if not self.mu_tdep_var.get():
            self._labeled(g1, "lbl_mu", "mu")                 # μ — константа
        else:
            rowmu = ttk.Frame(g1); rowmu.pack(fill="x", pady=(2, 0))
            ttk.Label(rowmu, text=self.t("lbl_mupair")).pack(side="left")
            cbmu = ttk.Combobox(rowmu, textvariable=self.mu_pair_var, state="readonly",
                                width=18, values=list(self.mu_tables))
            cbmu.pack(side="left", padx=(4, 0))
            cbmu.bind("<<ComboboxSelected>>", lambda e: self._on_param_edit())
            ttk.Button(g1, text=self.t("btn_mutables"), command=self.open_mu_library).pack(
                fill="x", pady=(2, 0))
        ttk.Button(g1, text=self.t("btn_mucalc"), command=self.open_mu_calc).pack(
            fill="x", pady=(2, 0))
        ttk.Checkbutton(g1, text=self.t("chk_feedsink"), variable=self.use_feedsink_var,
                        command=self._on_param_edit).pack(anchor="w", pady=(2, 0))

        gs = self._section(inner, self.t("grp_sub"), "substrate")
        ttk.Radiobutton(gs, text=self.t("rb_subsame"), value=True, variable=self.sub_same_var,
                        command=self._on_substrate_change).pack(anchor="w")
        ttk.Radiobutton(gs, text=self.t("rb_subown"), value=False, variable=self.sub_same_var,
                        command=self._on_substrate_change).pack(anchor="w")
        if not self.sub_same_var.get():
            self.sub_cb = ttk.Combobox(gs, textvariable=self.substrate_var, state="readonly",
                                       values=list(self.materials))
            self.sub_cb.pack(fill="x", pady=(2, 0))
            self.sub_cb.bind("<<ComboboxSelected>>", lambda e: self._on_sub_select())
            self._labeled(gs, "lbl_ksub", "k_sub")
            self._labeled(gs, "lbl_rhosub", "rho_sub")
            self._labeled(gs, "lbl_cpsub", "cp_sub")
            ttk.Button(gs, text=self.t("btn_savesub"), command=self.add_substrate).pack(
                fill="x", pady=(4, 0))

        if self.input_mode == "shoulder":
            gsh = self._section(inner, self.t("grp_shoe"), "shoe")
            self.shoe_cb = ttk.Combobox(gsh, textvariable=self.shoe_var, state="readonly",
                                        values=[SHOE_NONE] + list(self.materials))
            self.shoe_cb.pack(fill="x")
            self.shoe_cb.bind("<<ComboboxSelected>>", lambda e: self._on_shoe_change())
            if self.shoe_var.get() != SHOE_NONE:
                self._labeled(gsh, "lbl_kshoe", "k_shoe")
            ttk.Checkbutton(gsh, text=self.t("chk_bore"), variable=self.bore_var,
                            command=self._on_param_edit).pack(anchor="w", pady=(4, 0))

        gtd = self._section(inner, "k, cₚ(T)", "tdep")
        ttk.Checkbutton(gtd, text=self.t("chk_tdep"), variable=self.tdep_var,
                        command=self._on_param_edit).pack(anchor="w")
        ttk.Button(gtd, text=self.t("btn_tables"), command=self.open_library).pack(
            fill="x", pady=(4, 0))

        g2 = self._section(inner, self.t("grp_ranges"), "ranges")
        nrange = len(self._order())
        note = ("⚠ " + self.t("need2range")) if nrange < 2 else (self.t("matrix_n") % (3 ** nrange))
        ttk.Label(g2, text=note, foreground=("#b00" if nrange < 2 else "#555")).pack(anchor="w")

        def _param_block(sym):
            u = self._unit(sym)
            row = ttk.Frame(g2); row.pack(fill="x", pady=(4, 0))
            ttk.Label(row, text=self._disp(sym), width=4, anchor="w").pack(side="left")
            ttk.Radiobutton(row, text=self.t("rb_range"), value="range", variable=self.vary[sym],
                            command=lambda s=sym: self._on_vary_change(s)).pack(side="left")
            ttk.Radiobutton(row, text=self.t("rb_single"), value="fixed", variable=self.vary[sym],
                            command=lambda s=sym: self._on_vary_change(s)).pack(side="left")
            if self.vary[sym].get() == "range":
                kmin, kmax = RANGE_KEYS[sym]
                for cap, key in ((self.t("rng_min"), kmin), (self.t("rng_max"), kmax)):
                    r = ttk.Frame(g2); r.pack(fill="x")
                    ttk.Label(r, text=f"  {cap} [{u}]", width=16, anchor="w").pack(side="left")
                    e = ttk.Entry(r, textvariable=self._fields[key], width=8)
                    e.pack(side="left")
                    e.bind("<Return>", self._on_param_edit); e.bind("<FocusOut>", self._on_param_edit)
            else:
                r = ttk.Frame(g2); r.pack(fill="x")
                ttk.Label(r, text=f"  {self.t('rng_val')} [{u}]", width=16, anchor="w").pack(side="left")
                e = ttk.Entry(r, textvariable=self.fix_vars[sym], width=8)
                e.pack(side="left")
                e.bind("<Return>", lambda ev: self.build()); e.bind("<FocusOut>", lambda ev: self.build())

        for s in self._candidates():
            _param_block(s)
        if self.input_mode == "shoulder":
            self._labeled(g2, "lbl_rshoe", "R_shoe")

        g3 = self._section(inner, self.t("grp_view"), "view")
        rowv = ttk.Frame(g3); rowv.pack(fill="x", pady=1)
        ttk.Radiobutton(rowv, text=self.t("rb_2d"), value="2D", variable=self.view_var,
                        command=self._on_view_change).pack(side="left")
        ttk.Radiobutton(rowv, text=self.t("rb_3d"), value="3D", variable=self.view_var,
                        command=self._on_view_change).pack(side="left", padx=8)

        order = self._order()
        self._ensure_axes()
        disp_vals = [self._disp(s) for s in order]
        rev = {self._disp(s): s for s in order}      # отображаемое -> внутренний символ

        def _axis_combo(parent, axvar):
            cb = ttk.Combobox(parent, width=6, values=disp_vals, state="readonly")
            cb.set(self._disp(axvar.get()))

            def _on(_e):
                axvar.set(rev.get(cb.get(), cb.get()))
                self._on_axis_change()
            cb.bind("<<ComboboxSelected>>", _on)
            return cb

        rowx = ttk.Frame(g3); rowx.pack(fill="x", pady=1)
        ttk.Label(rowx, text=self.t("axis_x"), width=8, anchor="w").pack(side="left")
        _axis_combo(rowx, self.xaxis_var).pack(side="left")
        rowy = ttk.Frame(g3); rowy.pack(fill="x", pady=1)
        ttk.Label(rowy, text=self.t("axis_y"), width=8, anchor="w").pack(side="left")
        _axis_combo(rowy, self.yaxis_var).pack(side="left")

        # фиксированные значения остальных факторов (слайдеры)
        self.fix_scales = {}
        for fsym in self._fixed_factors():
            lo, hi = self._range(fsym)
            v = self.fix_vars[fsym]
            if not (lo <= v.get() <= hi):
                v.set(round(0.5 * (lo + hi), 3))
            rowfx = ttk.Frame(g3); rowfx.pack(fill="x", pady=1)
            ttk.Label(rowfx, text=f"{self.t('fix_lbl')} {self._disp(fsym)}=",
                      width=8, anchor="w").pack(side="left")
            ent = ttk.Entry(rowfx, textvariable=v, width=7)
            ent.pack(side="left")
            ent.bind("<Return>", lambda e: self.build())
            ttk.Label(rowfx, text=self._unit(fsym), width=6).pack(side="left")
            sc = ttk.Scale(g3, from_=lo, to=hi, orient="horizontal", variable=v)
            sc.pack(fill="x", pady=(0, 2))
            sc.bind("<ButtonRelease-1>", lambda e: self.build())
            self.fix_scales[fsym] = sc

        rowc = ttk.Frame(g3); rowc.pack(fill="x", pady=(4, 0))
        ttk.Label(rowc, text=self.t("lbl_color"), width=8, anchor="w").pack(side="left")
        ttk.Radiobutton(rowc, text=self.t("color_full"), value="full",
                        variable=self.colormode_var, command=self.build).pack(side="left")
        ttk.Radiobutton(rowc, text=self.t("color_win"), value="window",
                        variable=self.colormode_var, command=self.build).pack(side="left", padx=6)

        ttk.Button(inner, text=self.t("btn_build"), command=self.build).pack(
            fill="x", pady=(8, 6), padx=2)
        # колесо мыши над полями не меняет значения, а прокручивает левую панель
        self._lock_wheel(inner, self._left_canvas)

    def _style_header_text(self):
        arrow = "⊞" if self._style_collapsed else "⊟"
        view = self.view_var.get()
        return f"{arrow}  {self.t('lbl_style')}  ·  {view}"

    def _bind_panel_scroll(self, parent, canvas):
        """Колесо мыши над ЛЮБЫМ элементом панели прокручивает её (лёгкий скролл)."""
        if canvas is None:
            return

        def on_wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")
            return "break"

        def on_b4(e):
            canvas.yview_scroll(-1, "units"); return "break"

        def on_b5(e):
            canvas.yview_scroll(1, "units"); return "break"
        skip = ("TSpinbox", "Spinbox", "TCombobox", "TScale", "Scale", "TEntry", "Entry")
        for w in [parent] + list(self._descendants(parent)):
            if w.winfo_class() in skip:        # эти уже прокручивают панель через _lock_wheel
                continue
            w.bind("<MouseWheel>", on_wheel, add="+")
            w.bind("<Button-4>", on_b4, add="+")
            w.bind("<Button-5>", on_b5, add="+")

    def _rebuild_style_panel(self):
        """Пересобрать панель оформления (свои наборы для 2D и 3D)."""
        if not hasattr(self, "_sty_inner"):
            return
        for w in self._sty_inner.winfo_children():
            w.destroy()
        self._build_style_controls(self._sty_inner)
        self._lock_wheel(self._sty_inner, getattr(self, "_sty_canvas", None))
        self._bind_panel_scroll(self._sty_inner, getattr(self, "_sty_canvas", None))
        if hasattr(self, "_sty_btn"):
            self._sty_btn.config(text=self._style_header_text())
        if getattr(self, "_sty_canvas", None) is not None:
            self._sty_canvas.update_idletasks()
            self._sty_canvas.configure(scrollregion=self._sty_canvas.bbox("all"))

    def _build_style_controls(self, sty):
        """Группированный, интуитивный набор настроек: подпись приклеена к своему
           контролу; наборы для 2D и 3D — раздельные (не пересекаются)."""
        is3d = self.view_var.get() == "3D"

        def num(parent, label, var, lo, hi, inc):
            cell = ttk.Frame(parent); cell.pack(side="left", padx=6, pady=2)
            ttk.Label(cell, text=label).pack(side="left", padx=(0, 3))
            sp = ttk.Spinbox(cell, from_=lo, to=hi, increment=inc, width=5,
                             textvariable=var, command=self._on_textsize)
            sp.pack(side="left")
            sp.bind("<Return>", lambda e: self._on_textsize())
            sp.bind("<FocusOut>", lambda e: self._on_textsize())

        def chk(parent, label, var):
            ttk.Checkbutton(parent, text=label, variable=var,
                            command=self._on_textsize).pack(side="left", padx=6, pady=2)

        def slider(parent, label, var, a, b):
            cell = ttk.Frame(parent); cell.pack(side="left", padx=6, pady=2)
            ttk.Label(cell, text=label).pack(side="left", padx=(0, 3))
            ttk.Scale(cell, from_=a, to=b, orient="horizontal", length=90, variable=var,
                      command=lambda v: self._on_textsize()).pack(side="left")

        def group(title):
            g = ttk.Labelframe(sty, text=title, padding=4)
            g.pack(fill="x", pady=2, padx=2)
            r = ttk.Frame(g); r.pack(fill="x")
            return r

        # --- Текст и подписи ---
        r = group(self.t("sty_text"))
        c = ttk.Frame(r); c.pack(side="left", padx=6, pady=2)
        ttk.Label(c, text=self.t("lbl_txtsize")).pack(side="left", padx=(0, 3))
        ttk.Scale(c, from_=6, to=48, orient="horizontal", length=110, variable=self.plotfs_var,
                  command=lambda v: self._on_textsize()).pack(side="left")
        ttk.Spinbox(c, from_=6, to=72, width=4, textvariable=self.plotfs_var,
                    command=self._on_textsize).pack(side="left", padx=(3, 0))
        num(r, self.t("lbl_lblpad"), self.lblpad_var, 0, 40, 1)
        num(r, self.t("lbl_tickpad"), self.tickpad_var, 0, 40, 1)

        # --- Окно стабильности ---
        r = group(self.t("sty_window"))
        num(r, self.t("lbl_wlo"), self.wlo_var, 0.1, 1.2, 0.01)
        num(r, self.t("lbl_whi"), self.whi_var, 0.1, 1.5, 0.01)
        chk(r, self.t("lbl_radius"), self.toolrad_var)
        if not is3d:
            chk(r, self.t("lbl_winfill"), self.winfill_var)

        # --- Рамка фикс-параметров ---
        r = group(self.t("sty_box"))
        num(r, self.t("lbl_boxscale"), self.annotscale_var, 0.3, 3.0, 0.05)
        slider(r, self.t("lbl_boxx"), self.annotx_var, 0.0, 1.0)
        slider(r, self.t("lbl_boxy"), self.annoty_var, 1.0, 0.0)

        # --- Цветовая шкала ---
        r = group(self.t("sty_bar"))
        num(r, self.t("lbl_cbarpos"), self.cbar_pad_var, -0.02, 0.40, 0.01)
        num(r, self.t("lbl_cbpad"), self.cbar_lblx_var, -10.0, 16.0, 0.5)
        chk(r, self.t("lbl_cbflip"), self.cbar_flip_var)

        # --- Раздельно: 2D или 3D ---
        if is3d:
            r = group(self.t("sty_3d"))
            num(r, self.t("lbl_elev"), self.elev_var, 0, 90, 5)
            num(r, self.t("lbl_azim"), self.azim_var, -180, 180, 5)
            # плотность сетки 3D меняет разрешение -> нужен пересчёт (build)
            mc = ttk.Frame(r); mc.pack(side="left", padx=6, pady=2)
            ttk.Label(mc, text=self.t("lbl_mesh")).pack(side="left", padx=(0, 3))
            ttk.Spinbox(mc, from_=20, to=120, increment=4, width=5, textvariable=self.n3d_var,
                        command=self._on_mesh_change).pack(side="left")
        else:
            r = group(self.t("sty_2d"))
            num(r, self.t("lbl_ncolors"), self.nlev_var, 4, 256, 2)
            # аспект W:H (пресеты + два числа)
            c = ttk.Frame(r); c.pack(side="left", padx=6, pady=2)
            ttk.Label(c, text=self.t("lbl_aspect")).pack(side="left", padx=(0, 3))
            cb = ttk.Combobox(c, width=6, state="readonly",
                              values=["1:1", "5:4", "4:3", "3:2", "16:10", "16:9"])
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", lambda e: self._set_aspect_preset(cb.get()))
            spW = ttk.Spinbox(c, from_=0.1, to=99, increment=1, width=3,
                              textvariable=self.aspw_var, command=self._on_aspect_ratio)
            spW.pack(side="left", padx=(6, 0))
            ttk.Label(c, text=":").pack(side="left")
            spH = ttk.Spinbox(c, from_=0.1, to=99, increment=1, width=3,
                              textvariable=self.asph_var, command=self._on_aspect_ratio)
            spH.pack(side="left")
            for s in (spW, spH):
                s.bind("<Return>", lambda e: self._on_aspect_ratio())
                s.bind("<FocusOut>", lambda e: self._on_aspect_ratio())

        # --- Регрессия на карте ---
        r = group(self.t("sty_reg"))
        chk(r, self.t("lbl_showreg"), self.showreg_var)
        ttk.Button(r, text=self.t("btn_copyreg"),
                   command=self._copy_reduced_latex).pack(side="left", padx=8)

    def _toggle_style(self):
        self._style_collapsed = not self._style_collapsed
        if self._style_collapsed:
            self._sty_outer.pack_forget()
        else:
            self._sty_outer.pack(fill="x")
        self._sty_btn.config(text=self._style_header_text())

    def _build_plot_toolbar(self, parent):
        """Своя панель инструментов над графиком: цветные кнопки (делегируют
           стандартному matplotlib-тулбару) + заметная кнопка «Построить»."""
        tb = tk.Frame(parent, bg="#eef1f5")
        tb.pack(side="top", fill="x")
        efont = ("Segoe UI Emoji", self.ui_size + 5)
        cfont = (self.ui_family, max(7, self.ui_size - 3))

        def cell(emoji, caption, cmd, bg, fg):
            c = tk.Frame(tb, bg=bg, cursor="hand2", padx=7, pady=1, bd=1, relief="ridge")
            c.pack(side="left", padx=2, pady=2)
            l1 = tk.Label(c, text=emoji, bg=bg, fg=fg, font=efont)
            l1.pack()
            l2 = tk.Label(c, text=caption, bg=bg, fg="#333", font=cfont)
            l2.pack()
            for w in (c, l1, l2):
                w.bind("<Button-1>", lambda e: cmd())
                w.bind("<Enter>", lambda e, cc=c: cc.config(relief="solid"))
                w.bind("<Leave>", lambda e, cc=c: cc.config(relief="ridge"))
            return c

        def sep():
            tk.Frame(tb, bg="#c4ccd6", width=2).pack(side="left", fill="y", padx=5, pady=4)

        NAV, INT, VIEW, SAVE = "#dbe7f5", "#e6dcf2", "#fdeccb", "#dcefdc"
        cell("🏠", self.t("cap_reset"), self._nav.home, NAV, "#1565c0")
        cell("◀", self.t("cap_back"), self._nav.back, NAV, "#1565c0")
        cell("▶", self.t("cap_fwd"), self._nav.forward, NAV, "#1565c0")
        sep()
        cell("✋", self.t("cap_pan"), self._nav.pan, INT, "#6a3bb0")
        cell("🔍", self.t("cap_zoom"), self._nav.zoom, INT, "#6a3bb0")
        cell("⚙", self.t("cap_margins"), self._nav.configure_subplots, INT, "#6a3bb0")
        cell("🧹", self.t("cap_clear"), self._clear_points, INT, "#b5453b")
        sep()
        cell("▦", self.t("rb_2d"), lambda: (self.view_var.set("2D"), self._on_view_change()),
             VIEW, "#b8860b")
        cell("◳", self.t("rb_3d"), lambda: (self.view_var.set("3D"), self._on_view_change()),
             VIEW, "#b8860b")
        sep()
        cell("🖼", "PNG", self.save_png, SAVE, "#2e7d32")
        cell("📄", "PDF", self.save_pdf, SAVE, "#2e7d32")
        cell("⬡", "SVG", self.save_svg, SAVE, "#2e7d32")
        cell("🧮", "CSV", self.export_csv, SAVE, "#2e7d32")
        # заметная кнопка построения (акцент, справа)
        ttk.Button(tb, text=self.t("btn_build"), style="Accent.TButton",
                   command=self.build).pack(side="right", padx=6, pady=3)
        self._coord_lbl = tk.Label(tb, text="", bg="#eef1f5", fg="#666")
        self._coord_lbl.pack(side="right", padx=8)
        self.canvas.mpl_connect("motion_notify_event", self._on_coord)

    def _style_vars(self):
        """Переменные оформления, у которых СВОИ значения для 2D и 3D (не темп. окно)."""
        return {
            "plotfs": self.plotfs_var, "lblpad": self.lblpad_var, "tickpad": self.tickpad_var,
            "annotscale": self.annotscale_var, "annotx": self.annotx_var, "annoty": self.annoty_var,
            "cbar_pad": self.cbar_pad_var, "cbar_lblx": self.cbar_lblx_var,
            "cbar_flip": self.cbar_flip_var, "toolrad": self.toolrad_var, "showreg": self.showreg_var,
            "nlev": self.nlev_var, "winfill": self.winfill_var, "aspw": self.aspw_var,
            "asph": self.asph_var, "elev": self.elev_var, "azim": self.azim_var, "mesh": self.n3d_var,
        }

    def _save_style(self, view):
        for k, v in self._style_vars().items():
            try:
                self._style_store[view][k] = v.get()
            except tk.TclError:
                pass

    def _load_style(self, view):
        store = self._style_store.get(view, {})
        for k, v in self._style_vars().items():
            if k in store:
                try:
                    v.set(store[k])
                except tk.TclError:
                    pass
        # синхронизировать производные атрибуты
        self.plot_fs = self._iv(self.plotfs_var, self.plot_fs)
        self.n3d = self._iv(self.n3d_var, self.n3d)
        try:
            self.aspect_var.set(round(self._aspect_value(), 4))
        except tk.TclError:
            pass

    def _on_view_change(self):
        """Смена 2D/3D: сохранить настройки текущего вида, подгрузить настройки нового."""
        new = self.view_var.get()
        if new != self._prev_view:
            self._save_style(self._prev_view)
            self._load_style(new)
            self._prev_view = new
        self._rebuild_style_panel()
        self.build()

    def _on_mesh_change(self):
        """Плотность 3D-сетки: меняет разрешение -> полный пересчёт."""
        self.n3d = self._iv(self.n3d_var, self.n3d)
        self.build()

    def _on_coord(self, event):
        if event.inaxes is self.ax and event.xdata is not None:
            self._coord_lbl.config(text="x=%.3g  y=%.3g" % (event.xdata, event.ydata))
        else:
            self._coord_lbl.config(text="")

    def _tip(self, widget, text):
        """Простая всплывающая подсказка."""
        def enter(_e):
            if not text:
                return
            self._tipwin = tw = tk.Toplevel(widget); tw.wm_overrideredirect(True)
            x = widget.winfo_rootx() + 8; y = widget.winfo_rooty() + widget.winfo_height() + 2
            tw.wm_geometry("+%d+%d" % (x, y))
            tk.Label(tw, text=text, bg="#ffffe0", relief="solid", borderwidth=1,
                     font=(self.ui_family, self.ui_size - 1)).pack()

        def leave(_e):
            w = getattr(self, "_tipwin", None)
            if w is not None:
                w.destroy(); self._tipwin = None
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")

    def _build_right(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        tab_plot = ttk.Frame(nb)
        nb.add(tab_plot, text=self.t("tab_plot"))
        self.fig = Figure(figsize=(7, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=tab_plot)
        # стандартный тулбар matplotlib держим скрытым — делегируем ему действия
        self._navholder = ttk.Frame(tab_plot)
        self._nav = NavigationToolbar2Tk(self.canvas, self._navholder, pack_toolbar=False)
        # своя панель инструментов НАД графиком (цветные иконки + кнопка Plot)
        self._build_plot_toolbar(tab_plot)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        # интерактив точек: наведение -> крестик удаления; 2-й клик -> правка буквы
        self.canvas.mpl_connect("motion_notify_event", self._on_pt_motion)
        self.canvas.mpl_connect("button_press_event", self._on_pt_click)

        bottom = ttk.LabelFrame(tab_plot, text=self.t("grp_point"), padding=6)
        bottom.pack(fill="x", pady=4)
        # поля точки соответствуют активным факторам (учитывают тумблер v_f/F)
        pt_fields = [(self._disp(s), PT_KEY[s]) for s in self._candidates()]
        for lbl, key in pt_fields:
            ttk.Label(bottom, text=lbl).pack(side="left")
            ttk.Entry(bottom, textvariable=self._fields[key], width=7).pack(side="left", padx=(2, 8))
        # ширина валика w — только в расчёте точки, по галочке (иначе w = 2R)
        if self.input_mode == "kin":
            ttk.Checkbutton(bottom, text=self.t("chk_beadw"),
                            variable=self.beadw_on_var).pack(side="left", padx=(0, 2))
            ttk.Entry(bottom, textvariable=self._fields["w_bead"], width=6).pack(side="left", padx=(0, 8))
        ttk.Button(bottom, text=self.t("btn_calc"), command=self.calc_point).pack(side="left")
        ttk.Button(bottom, text=self.t("btn_clear_pts"),
                   command=self._clear_points).pack(side="left", padx=(4, 0))
        # результат — read-only поле со стрелками прокрутки по бокам (длинная строка)
        st = ttk.Style(self)
        st.configure("Result.TEntry", foreground="#0a7a2a")
        rfr = ttk.Frame(bottom); rfr.pack(side="left", fill="x", expand=True, padx=8)
        res_e = ttk.Entry(rfr, textvariable=self.result_var, state="readonly",
                          style="Result.TEntry", font=(self.ui_family, self.ui_size))
        ttk.Button(rfr, text="◀", width=2,
                   command=lambda: res_e.xview_scroll(-6, "units")).pack(side="left")
        res_e.pack(side="left", fill="x", expand=True)
        ttk.Button(rfr, text="▶", width=2,
                   command=lambda: res_e.xview_scroll(6, "units")).pack(side="left")

        # ---- оформление графика прямо у графика (перерисовка из кэша, без пересчёта) ----
        # сворачивается в тонкую полоску, чтобы не отнимать место у графика
        self.plotfs_var.set(self.plot_fs)
        stywrap = ttk.Frame(tab_plot); stywrap.pack(fill="x", pady=(2, 0))
        self._sty_btn = ttk.Button(stywrap, style="Toolbutton", command=self._toggle_style)
        self._sty_btn.pack(fill="x")
        # прокручиваемая область настроек (фикс. высота, чтобы не заслонять график)
        self._sty_outer = outer = ttk.Frame(stywrap, relief="groove", borderwidth=1)
        scanv = tk.Canvas(outer, height=190, highlightthickness=0)
        svsb = ttk.Scrollbar(outer, orient="vertical", command=scanv.yview)
        scanv.configure(yscrollcommand=svsb.set)
        svsb.pack(side="right", fill="y")
        scanv.pack(side="left", fill="both", expand=True)
        self._sty_canvas = scanv
        sty = ttk.Frame(scanv)
        self._sty_inner = sty
        swin = scanv.create_window((0, 0), window=sty, anchor="nw")
        sty.bind("<Configure>", lambda e: scanv.configure(scrollregion=scanv.bbox("all")))
        scanv.bind("<Configure>", lambda e: scanv.itemconfigure(swin, width=e.width))
        scanv.bind("<MouseWheel>", lambda e: scanv.yview_scroll(int(-e.delta / 120), "units"))
        self._sty_btn.config(text=self._style_header_text())
        if not self._style_collapsed:
            outer.pack(fill="x")
        self._build_style_controls(sty)
        self._lock_wheel(sty, self._sty_canvas)   # колесо над полями прокручивает панель
        self._bind_panel_scroll(sty, self._sty_canvas)   # и над любым другим элементом

        # экспорт PNG/PDF/SVG/CSV перенесён в верхнюю панель инструментов над графиком

        # --- вкладка: матрица планирования (+ регрессионное уравнение и экспорт LaTeX) ---
        tab_m = ttk.Frame(nb)
        nb.add(tab_m, text=self.t("tab_matrix"))
        topm = ttk.Frame(tab_m); topm.pack(fill="x", pady=4)
        ttk.Button(topm, text=self.t("mat_refresh"), command=self._refresh_matrix).pack(side="left", padx=2)
        ttk.Button(topm, text=self.t("mat_export"), command=self.export_matrix).pack(side="left", padx=2)
        ttk.Button(topm, text=self.t("btn_copyreg_full"), style="Accent.TButton",
                   command=self._copy_full_latex).pack(side="left", padx=8)
        # регрессионное уравнение — текстом в одну строку (читаемо, можно выделить/скопировать)
        reg = ttk.Labelframe(tab_m, text=self.t("reg_eq_title"), padding=6)
        reg.pack(fill="x", padx=6, pady=(2, 4))
        self.reg_units = ttk.Label(reg, text="", foreground="#888")
        self.reg_units.pack(anchor="w")
        self.reg_eq_var = tk.StringVar(value="")
        serif = ("Cambria", self.ui_size + 4)
        self.reg_eq_entry = ttk.Entry(reg, textvariable=self.reg_eq_var, font=serif,
                                      state="readonly", foreground="#111")
        self.reg_eq_entry.pack(fill="x", pady=(3, 0))
        ttk.Label(tab_m, text=self.t("mat_note"), justify="left",
                  foreground="#555").pack(fill="x", padx=6)

        mpa = self.t("unit_mpa")
        order = self._order()
        cols = [("run", "№", 40)]
        for i, s in enumerate(order):
            cols.append((f"x{i}", f"X{i+1}({s})", 50))
        for i, s in enumerate(order):
            cols.append((f"p{i}", f"{s}, {self._unit(s)}", 90))
        cols += [("tau", f"τ, {mpa}", 75), ("tc", "T_peak, °C", 85), ("tk", "T_peak, K", 85)]
        self.mat_cols = cols
        tree_frame = ttk.Frame(tab_m); tree_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self.matrix_tree = ttk.Treeview(tree_frame, columns=[c[0] for c in self.mat_cols],
                                        show="headings", height=27)
        for cid, head, w in self.mat_cols:
            self.matrix_tree.heading(cid, text=head)
            self.matrix_tree.column(cid, width=w, anchor="center", stretch=False)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.matrix_tree.yview)
        self.matrix_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.matrix_tree.pack(side="left", fill="both", expand=True)

    # ---------- relayout (язык/шрифты) ----------
    def _relayout(self):
        self._apply_fonts()
        self._build_menu()
        self.body.destroy()
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)
        self._build_body(self.body)
        self._update_title()
        self.build()

    def set_language(self, code):
        self.lang = code
        self._relayout()

    # ---------- helpers ----------
    def _f(self, key):
        return float(self._fields[key].get().replace(",", "."))

    def _read_params(self):
        # пруток (присадка): прочность + ρ,cₚ для стока подачи
        p = dict(sigma_ref=self._f("sigma_ref"), T_ref=self._f("T_ref"), m=self._f("m"),
                 T_solidus=self._f("T_solidus"), T0=self._f("T0"))
        p["rho_dep"] = self._f("rho")
        p["cp_dep"] = self._f("cp")
        # подложка: k, ρ, cₚ для кондукции (4kR) и числа Пекле (a = k/ρcₚ)
        if self.sub_same_var.get():
            p["k"] = self._f("k"); p["rho"] = self._f("rho"); p["cp"] = self._f("cp")
        else:
            p["k"] = self._f("k_sub"); p["rho"] = self._f("rho_sub"); p["cp"] = self._f("cp_sub")
        c_raw = self._fields["C_emp"].get().strip().replace(",", ".")
        p["C_emp"] = float(c_raw) if c_raw else None
        eta_raw = self._fields["eta"].get().strip().replace(",", ".")
        p["eta"] = float(eta_raw) if eta_raw else 1.0
        p["F"] = self._f("F") * 1e3                 # кН -> Н (осевая сила, форс-контрол)
        p["mu"] = self._f("mu")                     # коэф. трения контактной пары (константа)
        p["use_mu_tdep"] = bool(self.mu_tdep_var.get())
        p["mu_tab"] = self.mu_tables.get(self.mu_pair_var.get()) if p["use_mu_tdep"] else None
        p["v"] = self._f("v_dep") * 1e-3            # мм/с -> м/с
        p["use_pe"] = bool(self.use_pe_var.get())
        dep_mat = self.materials.get(self.preset_var.get(), {})
        p["poly"] = dep_mat.get("poly")
        # таблицы свойств: пруток (для стока) и подложка (для кондукции/Pe)
        if self.sub_same_var.get():
            sub_mat = dep_mat
        else:
            sub_mat = self.materials.get(self.substrate_var.get(), dep_mat)
        p["kt_sub"] = sub_mat.get("kt"); p["cpt_sub"] = sub_mat.get("cpt")
        p["cpt_dep"] = dep_mat.get("cpt"); p["kt_dep"] = dep_mat.get("kt")
        # теплопроводность ПРУТКА (для стока в патрон): из карточки материала
        # присадки; при sub_same она совпадает с k подложки
        p["k_dep"] = dep_mat.get("k", p["k"]) if not self.sub_same_var.get() else p["k"]
        p["use_tdep"] = bool(self.tdep_var.get())
        # вылет прутка L [мм] — включает сток в патрон S_rod (0/пусто = выключено)
        try:
            rl_raw = self._fields["rod_L"].get().strip().replace(",", ".") \
                     if "rod_L" in self._fields else ""
            p["rod_L"] = float(rl_raw) if rl_raw else 0.0
        except (ValueError, KeyError):
            p["rod_L"] = 0.0
        # шайба (отвод тепла вверх) — только в режиме shouldered
        if self.input_mode == "shoulder" and self.shoe_var.get() != SHOE_NONE:
            try:
                p["k2"] = self._f("k_shoe")
            except ValueError:
                p["k2"] = 0.0
        else:
            p["k2"] = 0.0
        return p

    def _ax_label(self, name):
        return self.t(AX_LABEL_KEY[name])

    def _unit(self, name):
        return self.t(AX_UNIT_KEY[name])

    # журнальные (англ.) подписи осей: (Название, символ-mathtext, единицы)
    JLAB = {"ω": ("Rotational Speed", r"\omega", "rev/min"),
            "R": ("Tool Radius", "R", "mm"),
            "H": ("Gap", "H", "mm"),
            "vz": ("Feed Velocity", "v_{f}", "mm/s"),
            "vx": ("Traverse Velocity", "v_{t}", "mm/s"),
            "D": ("Tool Diameter", "D", "mm"),
            "a": ("Bar Side", "a", "mm"),
            "F": ("Axial Force", "F", "kN")}

    # mathtext-символы факторов (v↓→v_f, v→→v_t — как в графике)
    AX_MATH = {"ω": r"\omega", "R": "R", "H": "H",
               "vz": "v_{f}", "vx": "v_{t}", "D": "D", "a": "a", "F": "F"}
    # короткое отображение в UI (выпадающие списки осей, ползунки фикс-значений)
    SYM_DISP = {"vz": "v_f", "vx": "v_t"}

    def _disp(self, sym):
        return self.SYM_DISP.get(sym, sym)

    @staticmethod
    def _iv(var, default):
        try:
            return int(round(float(var.get())))
        except (ValueError, tk.TclError):
            return default

    @staticmethod
    def _fv(var, default):
        try:
            return float(var.get())
        except (ValueError, tk.TclError):
            return default

    def _wfracs(self):
        """Настраиваемые доли окна (нижняя, верхняя) ×T_solidus."""
        lo = self._fv(self.wlo_var, 0.6)
        hi = self._fv(self.whi_var, 0.9)
        if hi <= lo:                       # защита от инверсии
            lo, hi = 0.6, 0.9
        return lo, hi

    def _window_C(self, T_sol_C):
        """Границы технологического окна в °C.

        Гомологическая температура определена на АБСОЛЮТНОЙ шкале:
            T_lo = lo·T_s,  T_hi = hi·T_s,   T_s в кельвинах,
        а результат переводится обратно в °C. Прямое умножение долей на
        температуру солидуса в °C дало бы другое окно (для AA6082: 351–526 °C
        вместо 242–499 °C) и не было бы гомологическим критерием."""
        lo, hi = self._wfracs()
        Ts_K = c_to_k(float(T_sol_C))
        return lo * Ts_K - 273.15, hi * Ts_K - 273.15

    def _plot_label(self, name):
        n, sym, u = self.JLAB[name]
        if name == "D" and self.toolrad_var.get():        # радиус вместо диаметра
            n, sym = "Tool Radius", "R"
        return r"%s, $%s$ (%s)" % (n, sym, u)

    def _plot_annot(self, name, val):
        n, sym, u = self.JLAB[name]
        if name == "D" and self.toolrad_var.get():
            n, sym, val = "Tool Radius", "R", val / 2.0
        return r"%s, $%s$ = %g %s" % (n, sym, val, u)

    def _load_preset(self):
        pr = self.materials[self.preset_var.get()]
        for key in ("sigma_ref", "T_ref", "m", "k", "T_solidus", "T0"):
            self._fields[key].set(str(pr[key]))
        self._fields["rho"].set(str(pr.get("rho", 2700.0)))
        self._fields["cp"].set(str(pr.get("cp", 900.0)))
        self._fields["C_emp"].set("" if pr.get("C_emp") is None else str(pr["C_emp"]))
        self.model_key = "phys"          # оба процесса — физическая модель
        self.build()

    def _on_substrate_change(self):
        """Переключатель «подложка = пруток / своя»: при «своя» подставить свойства
           выбранного материала, затем перестроить (показать/скрыть поля)."""
        if not self.sub_same_var.get():
            self._fill_sub_fields()
        self._relayout()

    def _fill_sub_fields(self):
        name = self.substrate_var.get()
        if name in self.materials:
            pr = self.materials[name]
            self._fields["k_sub"].set(str(pr["k"]))
            self._fields["rho_sub"].set(str(pr.get("rho", 2700.0)))
            self._fields["cp_sub"].set(str(pr.get("cp", 900.0)))

    def _on_sub_select(self):
        self._fill_sub_fields()
        self._on_param_edit()

    def add_substrate(self):
        """Сохранить текущие свойства подложки (k, ρ, cₚ) как новый материал в базе."""
        name = simpledialog.askstring(self.t("btn_savesub"), self.t("ask_matname"), parent=self)
        if not name:
            return
        try:
            k, rho, cp = self._f("k_sub"), self._f("rho_sub"), self._f("cp_sub")
        except ValueError:
            messagebox.showerror(self.t("err"), self.t("err_num"))
            return
        b = dict(self.materials.get(self.preset_var.get(), {}))   # σ,m,Tsol — от прутка (заглушка)
        entry = dict(sigma_ref=b.get("sigma_ref", 250.0), T_ref=b.get("T_ref", 600.0),
                     m=b.get("m", 1.0), k=k, T_solidus=b.get("T_solidus", 580.0), T0=25.0,
                     rho=rho, cp=cp, C_emp=None, poly=None)
        user = load_user_materials(); user[name] = entry; save_user_materials(user)
        self.materials = all_materials()
        self.substrate_var.set(name)
        messagebox.showinfo(self.t("saved"), self.t("mat_added"))
        self._relayout()

    def _on_mu_mode(self):
        """Переключение μ: константа <-> таблица μ(T). В режиме таблицы — валидная пара."""
        if self.mu_tdep_var.get() and self.mu_pair_var.get() not in self.mu_tables:
            if self.mu_tables:
                self.mu_pair_var.set(next(iter(self.mu_tables)))
        self._relayout()

    def _on_shoe_change(self):
        name = self.shoe_var.get()
        if name != SHOE_NONE and name in self.materials:
            self._fields["k_shoe"].set(str(self.materials[name]["k"]))
        self._relayout()        # показать/скрыть поле k шайбы

    def add_material(self):
        name = simpledialog.askstring(self.t("btn_addmat"), self.t("ask_matname"), parent=self)
        if not name:
            return
        try:
            entry = dict(sigma_ref=self._f("sigma_ref"), T_ref=self._f("T_ref"),
                         m=self._f("m"), k=self._f("k"), T_solidus=self._f("T_solidus"),
                         T0=self._f("T0"), rho=self._f("rho"), cp=self._f("cp"),
                         C_emp=None, poly=None)
        except ValueError:
            messagebox.showerror(self.t("err"), self.t("err_num"))
            return
        user = load_user_materials()
        user[name] = entry
        save_user_materials(user)
        self.materials = all_materials()
        self.preset_var.set(name)
        messagebox.showinfo(self.t("saved"), self.t("mat_added"))
        self._relayout()

    @staticmethod
    def _parse_table(tw):
        out = []
        for line in tw.get("1.0", "end").strip().splitlines():
            pr = line.replace(",", " ").split()
            if len(pr) >= 2:
                try:
                    out.append([float(pr[0]), float(pr[1])])
                except ValueError:
                    pass
        out.sort()
        return out or None

    def open_library(self):
        """Библиотека температурозависимых свойств: список материалов слева,
           редактирование таблиц k(T), cₚ(T) справа; создание/удаление своих."""
        win = tk.Toplevel(self); win.title(self.t("lib_title"))
        win.transient(self); win.geometry("760x560")
        cur = {"name": self.preset_var.get()}
        uf = (self.ui_family, self.ui_size)
        mono = ("Consolas", max(9, self.ui_size))

        left = ttk.Frame(win, padding=8); left.pack(side="left", fill="y")
        ttk.Label(left, text=self.t("lib_materials")).pack(anchor="w")
        lb = tk.Listbox(left, width=26, height=22, exportselection=False, font=uf)
        lb.pack(fill="y", expand=True)
        bl = ttk.Frame(left); bl.pack(fill="x", pady=4)

        right = ttk.Frame(win, padding=8); right.pack(side="left", fill="both", expand=True)
        title_lbl = ttk.Label(right, text="", font=(self.ui_family, self.ui_size, "bold"))
        title_lbl.pack(anchor="w")
        ttk.Label(right, text=self.t("lib_kT")).pack(anchor="w", pady=(6, 0))
        t_k = tk.Text(right, height=9, font=mono); t_k.pack(fill="x")
        ttk.Label(right, text=self.t("lib_cpT")).pack(anchor="w", pady=(6, 0))
        t_cp = tk.Text(right, height=9, font=mono); t_cp.pack(fill="x")

        def reload_list(select=None):
            lb.delete(0, "end")
            for nm in self.materials:
                lb.insert("end", nm)
            tgt = select or cur["name"]
            if tgt in self.materials:
                i = list(self.materials).index(tgt)
                lb.selection_clear(0, "end"); lb.selection_set(i); lb.see(i)

        def fill(tw, table):
            tw.delete("1.0", "end")
            if table:
                tw.insert("1.0", "\n".join(f"{r[0]:g} {r[1]:g}" for r in table))

        def load_sel(*_):
            sel = lb.curselection()
            if not sel:
                return
            nm = lb.get(sel[0]); cur["name"] = nm
            mat = self.materials.get(nm, {})
            title_lbl.config(text=nm)
            fill(t_k, mat.get("kt")); fill(t_cp, mat.get("cpt"))
        lb.bind("<<ListboxSelect>>", load_sel)

        def save_cur():
            nm = cur["name"]; b = dict(self.materials.get(nm, {}))
            entry = dict(sigma_ref=b.get("sigma_ref"), T_ref=b.get("T_ref"), m=b.get("m"),
                         k=b.get("k"), T_solidus=b.get("T_solidus"), T0=b.get("T0", 25.0),
                         rho=b.get("rho"), cp=b.get("cp"), C_emp=b.get("C_emp"),
                         poly=b.get("poly"), kt=self._parse_table(t_k), cpt=self._parse_table(t_cp))
            user = load_user_materials(); user[nm] = entry; save_user_materials(user)
            self.materials = all_materials(); reload_list(nm)
            messagebox.showinfo(self.t("saved"), self.t("mat_added"), parent=win)

        def new_mat():
            name = simpledialog.askstring(self.t("lib_new"), self.t("ask_matname"), parent=win)
            if not name:
                return
            b = dict(self.materials.get(cur["name"], {}))
            entry = dict(sigma_ref=b.get("sigma_ref", 250.0), T_ref=b.get("T_ref", 600.0),
                         m=b.get("m", 1.0), k=b.get("k", 100.0),
                         T_solidus=b.get("T_solidus", 560.0), T0=b.get("T0", 25.0),
                         rho=b.get("rho", 4000.0), cp=b.get("cp", 600.0), C_emp=None, poly=None,
                         kt=self._parse_table(t_k), cpt=self._parse_table(t_cp))
            user = load_user_materials(); user[name] = entry; save_user_materials(user)
            self.materials = all_materials(); cur["name"] = name
            reload_list(name); load_sel()

        def del_mat():
            nm = cur["name"]; user = load_user_materials()
            if nm not in user:
                messagebox.showwarning(self.t("err"), self.t("lib_del_builtin"), parent=win)
                return
            del user[nm]; save_user_materials(user)
            self.materials = all_materials()
            cur["name"] = next(iter(self.materials))
            reload_list(); load_sel()

        ttk.Button(bl, text=self.t("lib_new"), command=new_mat).pack(fill="x", pady=1)
        ttk.Button(bl, text=self.t("lib_del"), command=del_mat).pack(fill="x", pady=1)

        def close(apply_name=None):
            win.destroy()
            self.materials = all_materials()
            self._relayout()
            if apply_name:
                self.preset_var.set(apply_name)
                self.tdep_var.set(True)
                self._load_preset()

        br = ttk.Frame(right); br.pack(fill="x", pady=10)
        ttk.Button(br, text=self.t("lib_save"), command=save_cur).pack(side="left")
        ttk.Button(br, text=self.t("lib_apply"),
                   command=lambda: close(cur["name"])).pack(side="left", padx=6)
        ttk.Button(br, text=self.t("set_cancel"), command=lambda: close()).pack(side="right")

        reload_list()
        win.after(60, load_sel)
        self._lock_wheel(win)
        win.grab_set()

    def open_mu_library(self):
        """Редактор таблиц μ(T): список пар слева, таблица «T μ» справа;
           правка существующих, создание новых, удаление своих (user_mu.json)."""
        win = tk.Toplevel(self); win.title(self.t("mu_title"))
        win.transient(self); win.geometry("560x520")
        uf = (self.ui_family, self.ui_size)
        mono = ("Consolas", max(9, self.ui_size))
        cur = {"name": self.mu_pair_var.get() if self.mu_pair_var.get() in self.mu_tables
               else (next(iter(self.mu_tables)) if self.mu_tables else "")}

        left = ttk.Frame(win, padding=8); left.pack(side="left", fill="y")
        ttk.Label(left, text=self.t("mu_pairs")).pack(anchor="w")
        lb = tk.Listbox(left, width=24, height=20, exportselection=False, font=uf)
        lb.pack(fill="y", expand=True)
        bl = ttk.Frame(left); bl.pack(fill="x", pady=4)

        right = ttk.Frame(win, padding=8); right.pack(side="left", fill="both", expand=True)
        title_lbl = ttk.Label(right, text="", font=(self.ui_family, self.ui_size, "bold"))
        title_lbl.pack(anchor="w")
        ttk.Label(right, text=self.t("mu_hint")).pack(anchor="w", pady=(6, 0))
        t_mu = tk.Text(right, height=16, font=mono); t_mu.pack(fill="both", expand=True)

        def reload_list(select=None):
            lb.delete(0, "end")
            for nm in self.mu_tables:
                lb.insert("end", nm)
            tgt = select or cur["name"]
            if tgt in self.mu_tables:
                i = list(self.mu_tables).index(tgt)
                lb.selection_clear(0, "end"); lb.selection_set(i); lb.see(i)

        def load_sel(*_):
            sel = lb.curselection()
            if not sel:
                return
            nm = lb.get(sel[0]); cur["name"] = nm
            title_lbl.config(text=nm)
            t_mu.delete("1.0", "end")
            t_mu.insert("1.0", "\n".join(f"{r[0]:g} {r[1]:g}" for r in self.mu_tables.get(nm, [])))
        lb.bind("<<ListboxSelect>>", load_sel)

        def save_cur(name=None):
            nm = name or cur["name"]
            tab = self._parse_table(t_mu)
            if not tab:
                messagebox.showwarning(self.t("err"), self.t("mu_empty"), parent=win)
                return
            user = load_user_mu(); user[nm] = tab; save_user_mu(user)
            self.mu_tables = all_mu_tables(); cur["name"] = nm
            reload_list(nm)
            messagebox.showinfo(self.t("saved"), nm, parent=win)

        def new_pair():
            name = simpledialog.askstring(self.t("mu_new"), self.t("mu_askname"), parent=win)
            if not name:
                return
            if not t_mu.get("1.0", "end").strip():
                t_mu.insert("1.0", "25 0.5\n300 0.42\n560 0.32")
            save_cur(name)

        def del_pair():
            nm = cur["name"]; user = load_user_mu()
            if nm not in user:
                messagebox.showwarning(self.t("err"), self.t("mu_del_builtin"), parent=win)
                return
            del user[nm]; save_user_mu(user)
            self.mu_tables = all_mu_tables()
            cur["name"] = next(iter(self.mu_tables)) if self.mu_tables else ""
            reload_list(); load_sel()

        ttk.Button(bl, text=self.t("mu_new"), command=new_pair).pack(fill="x", pady=1)
        ttk.Button(bl, text=self.t("lib_del"), command=del_pair).pack(fill="x", pady=1)

        def close(apply_name=None):
            win.destroy()
            self.mu_tables = all_mu_tables()
            if apply_name:
                self.mu_pair_var.set(apply_name)
                self.mu_tdep_var.set(True)
            self._relayout()

        br = ttk.Frame(right); br.pack(fill="x", pady=10)
        ttk.Button(br, text=self.t("lib_save"), command=lambda: save_cur()).pack(side="left")
        ttk.Button(br, text=self.t("lib_apply"),
                   command=lambda: close(cur["name"])).pack(side="left", padx=6)
        ttk.Button(br, text=self.t("set_cancel"), command=lambda: close()).pack(side="right")

        reload_list()
        win.after(60, load_sel)
        self._lock_wheel(win)
        win.grab_set()

    def open_mu_calc(self):
        """Маленький калькулятор μ из крутящего момента и силы прижима.
           M = (2/3)·μ·F·Rc (скольжение) -> μ = 3M / (2·F·Rc). Не заслоняет график."""
        win = tk.Toplevel(self); win.title(self.t("muc_title"))
        win.transient(self); win.resizable(False, False)
        uf = (self.ui_family, self.ui_size)
        vM = tk.StringVar(value="10"); vF = tk.StringVar(value="8"); vRc = tk.StringVar(value="10")
        res = tk.StringVar(value="μ = —")
        rows = [(self.t("muc_M"), vM), (self.t("muc_F"), vF), (self.t("muc_Rc"), vRc)]
        for i, (lab, var) in enumerate(rows):
            ttk.Label(win, text=lab, anchor="w").grid(row=i, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(win, textvariable=var, width=10).grid(row=i, column=1, padx=8, pady=4)

        def calc(*_):
            try:
                M = float(vM.get().replace(",", "."))
                F = float(vF.get().replace(",", ".")) * 1e3      # кН -> Н
                Rc = float(vRc.get().replace(",", ".")) * 1e-3   # мм -> м
                mu = 3.0 * M / (2.0 * F * Rc) if (F > 0 and Rc > 0) else float("nan")
                res.set("μ = %.3f" % mu if mu == mu else "μ = —")
                return mu if mu == mu else None
            except ValueError:
                res.set("μ = —"); return None
        for _, var in rows:
            var.trace_add("write", calc)
        ttk.Label(win, textvariable=res, font=(self.ui_family, self.ui_size + 1, "bold"),
                  foreground="#0a3").grid(row=3, column=0, columnspan=2, pady=(6, 2))
        ttk.Label(win, text="μ = 3M / (2·F·R_c)", foreground="#777").grid(
            row=4, column=0, columnspan=2)

        def use_mu():
            mu = calc()
            if mu is not None:
                self._fields["mu"].set("%.3f" % mu)
                self.mu_tdep_var.set(False)
                win.destroy(); self._on_param_edit()
        br = ttk.Frame(win); br.grid(row=5, column=0, columnspan=2, pady=8)
        ttk.Button(br, text=self.t("muc_use"), command=use_mu).pack(side="left", padx=4)
        ttk.Button(br, text=self.t("set_cancel"), command=win.destroy).pack(side="left", padx=4)
        calc()
        self._lock_wheel(win)
        win.update_idletasks()

    def _on_model_change(self):
        self.model_key = self._model_from_label(self.model_cb_var.get())
        self.build()


    # ---------- матрица планирования ----------
    def _tau_at(self, T, p, Rc_mm=None):
        """Контактное касательное τ_c [МПа] при T: min(μ·p_контакт, τ_yield).
           τ_yield размягчается по солидусу; при заданном Rc учитывается p=F/(πRc²)."""
        ratio = max(0.0, (T - p["T0"]) / (p["T_solidus"] - p["T0"]))
        soft = max(0.0, 1.0 - ratio ** p["m"])
        tau_y = p["sigma_ref"] * soft / SQRT3                 # МПа
        if Rc_mm:
            Rc = Rc_mm * 1e-3
            p_contact = p.get("F", 0.0) / (math.pi * max(Rc, 1e-9) ** 2) / 1e6   # МПа
            mu = p.get("mu", 0.5)
            if p.get("use_mu_tdep") and p.get("mu_tab"):
                mu = float(interp_prop(p["mu_tab"], mu, T))
            return min(mu * p_contact, tau_y)
        return tau_y

    def _levels(self):
        """Уровни −1/0/+1 (min/середина/max) для 3 активных факторов режима."""
        order = self._order()
        lv = {}
        for s in order:
            lo, hi = self._f(RANGE_KEYS[s][0]), self._f(RANGE_KEYS[s][1])
            lv[s] = [lo, 0.5 * (lo + hi), hi]
        return order, lv

    def _matrix_rows(self):
        """Полный план 3^N (N = число «диапазонных» параметров): кодир. факторы,
           реальные значения, τ, T_peak. Фикс-параметры держатся константами."""
        try:
            p = self._read_params()
            order, lv = self._levels()
        except (ValueError, KeyError):
            return []
        rows, n = [], 0
        for idx in itertools.product(range(3), repeat=len(order)):
            n += 1
            vals = self._all_vals({order[j]: lv[order[j]][idx[j]] for j in range(len(order))})
            omega, R, H, pe = self._resolve(p, vals)
            T = compute_T(omega, R, H, pe, self.model_key)
            tau = self._tau_at(T, pe, R)
            codes = tuple(i - 1 for i in idx)
            reals = tuple(vals[s] for s in order)
            rows.append((n, codes, reals, tau, T, c_to_k(T)))
        return rows

    def _fit_regression(self):
        """МНК-полином T_peak по 3^N точкам в координатах активных факторов.
           Возвращает (c0, lin[N], quad[N], inter[pairs], order)."""
        try:
            p = self._read_params()
            order, lv = self._levels()
        except (ValueError, KeyError):
            return None
        N = len(order)
        F = [[] for _ in range(N)]
        for idx in itertools.product(range(3), repeat=N):
            for j in range(N):
                F[j].append(lv[order[j]][idx[j]])
        F = [np.array(c) for c in F]
        Ts = []
        for kk in range(len(F[0])):
            vals = self._all_vals({order[j]: F[j][kk] for j in range(N)})
            omega, R, H, pe = self._resolve(p, vals)
            Ts.append(float(compute_T(omega, R, H, pe, self.model_key)))
        T = np.array(Ts)
        pairs = list(itertools.combinations(range(N), 2))
        A = [np.ones_like(F[0])] + F + [F[j] * F[j] for j in range(N)]
        A += [F[a] * F[b] for a, b in pairs]
        c, *_ = np.linalg.lstsq(np.column_stack(A), T, rcond=None)
        c = [round(float(v), 6) for v in c]
        lin = c[1:1 + N]
        quad = c[1 + N:1 + 2 * N]
        inter = c[1 + 2 * N:]
        return (c[0], lin, quad, inter, order)

    def _refresh_matrix(self):
        if not hasattr(self, "matrix_tree"):
            return
        self.matrix_tree.delete(*self.matrix_tree.get_children())
        code = lambda x: "0" if x == 0 else f"{x:+d}"
        for r in self._matrix_rows():
            n, codes, reals, tau, Tc, Tk = r
            vals = ([n] + [code(c) for c in codes] + [f"{v:g}" for v in reals]
                    + [f"{tau:.2f}", f"{Tc:.1f}", f"{Tk:.1f}"])
            self.matrix_tree.insert("", "end", values=vals)
        self._render_regression()

    # отображаемые символы факторов в текстовом уравнении (Unicode)
    UNI = {"ω": "ω", "vz": "v_f", "vx": "v_t", "D": "D", "H": "H", "a": "a", "F": "F", "R": "R"}

    @staticmethod
    def _poly_text(c0, lin, quad, inter, syms):
        """Полином одной строкой: T_peak = c0 + a·ω + … (² для квадратов, · для произведений)."""
        N = len(syms)
        terms = [(c0, "")]
        terms += [(lin[j], syms[j]) for j in range(N)]
        terms += [(quad[j], syms[j] + "²") for j in range(N)]
        pairs = list(itertools.combinations(range(N), 2))
        terms += [(inter[i], syms[a] + "·" + syms[b]) for i, (a, b) in enumerate(pairs)]
        out, first = "T_peak = ", True
        for coef, sym in terms:
            if coef == 0:
                continue
            sign = "−" if coef < 0 else "+"
            body = (f"{abs(coef):g}·{sym}") if sym else f"{abs(coef):g}"
            if first:
                out += ("−" + body) if sign == "−" else body
                first = False
            else:
                out += " " + sign + " " + body
        return out if not first else "T_peak = 0"

    def _render_regression(self):
        """Регрессионное уравнение текстом (одна строка) + LaTeX в _full_reg_latex."""
        if not hasattr(self, "reg_eq_var"):
            return
        self._full_reg_latex = None
        try:
            order = self._order()
            poly = self.materials.get(self.preset_var.get(), {}).get("poly")
            if poly and self.input_mode == "H":
                c0 = poly["c0"]; lin = [poly["w"], poly["R"], poly["H"]]
                quad = [poly["w2"], poly["R2"], poly["H2"]]
                inter = [poly["wR"], poly["wH"], poly["RH"]]
                syms_u = ["ω", "R", "H"]; syms_l = [r"\omega", "R", "H"]
            else:
                fit = self._fit_regression()
                if not fit:
                    raise ValueError
                c0, lin, quad, inter, _ = fit
                syms_u = [self.UNI[s] for s in order]
                syms_l = [self.AX_MATH[s] for s in order]
            text = self._poly_text(c0, lin, quad, inter, syms_u)
            self._full_reg_latex = self._regression_latex(c0, lin, quad, inter, syms_l)
            units = "[ " + ";  ".join("%s: %s" % (self.UNI.get(s, s), self._unit(s))
                                      for s in order) + " ]"
        except Exception:
            text, units = self.t("need2range"), ""
        self.reg_units.config(text=units)
        self.reg_eq_var.set(text)

    def export_matrix(self):
        rows = self._matrix_rows()
        if not rows:
            messagebox.showwarning(self.t("no_data"), self.t("no_data_msg"))
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="afsd_design_matrix.csv")
        if not path:
            return
        order = self._order()
        N = len(order)
        with open(path, "w", encoding="utf-8") as fh:
            head = (["run"] + ["X%d" % (i + 1) for i in range(N)] + list(order)
                    + ["tau_MPa", "Tpeak_C", "Tpeak_K"])
            fh.write(",".join(head) + "\n")
            for n, codes, reals, tau, Tc, Tk in rows:
                vals = ([str(n)] + [str(c) for c in codes] + ["%g" % v for v in reals]
                        + ["%.4f" % tau, "%.3f" % Tc, "%.3f" % Tk])
                fh.write(",".join(vals) + "\n")
        messagebox.showinfo(self.t("saved"), path)

    # ---------- расчёт точки ----------
    def calc_point(self):
        try:
            p = self._read_params()
            # точка задаётся по ВСЕМ кандидатам (поля pt_*)
            vals = {s: self._f(PT_KEY[s]) for s in self._candidates()}
        except (ValueError, KeyError):
            messagebox.showerror(self.t("err"), self.t("err_num"))
            return
        omega, R, H, pe = self._resolve(p, vals, point=True)
        T, aud = compute_T_audit(omega, R, H, pe)       # T_peak + аудит решателя
        Tmin, Tmax = self._window_C(p["T_solidus"])
        status = (self.t("st_in") if Tmin <= T <= Tmax else
                  (self.t("st_below") if T < Tmin else self.t("st_above")))
        extra = ""
        # сток в патрон показываем ПЕРВЫМ: строка результата длинная и хвост
        # уезжает за правый край поля, а η_экв — самое важное при L > 0
        if aud.get("sink_rod", 0.0) > 0.0:
            extra += (f"   η_экв={aud['eta_rod']:.2f} (L={self._fields['rod_L'].get()} мм,"
                      f" S_rod={aud['sink_rod']:.3f} Вт/К, Pe_L={aud['Pe_L']:.2f})")
        if self.input_mode == "kin":
            wb_used = self._f("w_bead") if self.beadw_on_var.get() else 2.0 * R
            extra += f"   H={H:.2f} мм   w={wb_used:.2f} мм"
        elif self.input_mode == "shoulder":
            extra += f"   R_eff={R:.2f} мм"
        extra += f"   Pe={aud['Pe']:.2f}, G={aud['G']:.2f}"
        regime = self.t("reg_slide") if aud["branch"] == "sliding" else self.t("reg_stick")
        extra += (f"   p={aud['p_contact']:.0f}, τc={aud['tau_c']:.0f} МПа"
                  f" ({regime}, T*={aud['Tstar']:.0f}°C)")
        if aud["solidus_flag"]:
            extra += "   ⚠ " + self.t("flag_solidus")
        if aud.get("sink_rod", 0.0) > 0.0:
            extra += (f"   α/v_f={aud['rod_reach_mm']:.0f} мм,"
                      f" σ={aud['sigma_adv']:.2f}, Pe_D={aud['Pe_D']:.1f}")
        # аудит решателя в консоль (физика проверяема: ветвь, T*, τ, Q, стоки, Pe, G).
        # Печать защищена: консоль Windows бывает в cp1251, где нет τ/α/η, и
        # UnicodeEncodeError не должен ронять расчёт точки.
        _audit_msg = ("[AFSD audit] branch=%s  T_peak=%.1f°C  T*=%.1f  T_slide=%.1f  "
                      "τc=%.1f τy=%.1f MPa  p=%.1f MPa  μ=%.3f  Q=%.1f W  "
                      "sink=%.4f (cond=%.4f shoe=%.4f adv=%.4f rod=%.4f) W/K  "
                      "α/v_f=%.1f mm  η_экв=%.3f  Pe=%.2f G=%.3f  solidus_flag=%s"
                      % (aud["branch"], T, aud["Tstar"], aud["Tslide"], aud["tau_c"], aud["tau_y"],
                         aud["p_contact"], aud["mu_eff"], aud["Q"], aud["sink"], aud["sink_cond"],
                         aud["sink_shoe"], aud["sink_adv"], aud.get("sink_rod", 0.0),
                         aud.get("rod_reach_mm", float("nan")), aud.get("eta_rod", 1.0),
                         aud["Pe"], aud["G"], aud["solidus_flag"]))
        try:
            print(_audit_msg)
        except UnicodeEncodeError:                    # консоль не тянет юникод
            enc = (getattr(sys.stdout, "encoding", None) or "ascii")
            print(_audit_msg.encode(enc, "replace").decode(enc, "replace"))
        except Exception:                             # stdout может отсутствовать (.exe)
            pass
        self.result_var.set(f"T_peak = {T:.1f} °C  ({c_to_k(T):.1f} K)   "
                            f"[{self.t('res_window')} {Tmin:.0f}…{Tmax:.0f} °C]  {status}{extra}")
        # накапливаем точки: новая не убирает прежние, ей даётся следующая буква.
        # повтор того же набора параметров не плодит дубликат (обновляем последнюю).
        newvals = {k: float(v) for k, v in vals.items()}
        if self._points and self._points[-1]["vals"] == newvals:
            self._points[-1]["T"] = float(T)
        else:
            self._points.append(dict(label=self._next_label(), vals=newvals, T=float(T)))
        self._hover_idx = None
        self.build()

    # ---------- интерактивные точки на карте ----------
    def _next_label(self):
        used = {p["label"] for p in self._points}
        A = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        for c in A + [a + b for a in A for b in A]:
            if c not in used:
                return c
        return "P%d" % (len(self._points) + 1)

    def _clear_points(self):
        self._points = []
        self._hover_idx = None
        self.build()

    def _nav_active(self):
        tb = getattr(self, "_nav", None)
        return bool(tb and getattr(tb, "mode", ""))

    def _point_geom(self, xN, yN, X=None, Y=None):
        """Геометрия видимых точек: idx -> (px, py, ox, oy, w_px, text).
           Точка (маркер) — в координатах (px,py); рамка с цифрой — справа от неё,
           совпадающие по координатам подписи каскадируются вверх, чтобы не слипались."""
        fs = self.plot_fs
        LBL_OX = 13                                  # рамка правее маркера (точка слева)
        geom, seen = {}, {}
        for i, pt in enumerate(self._points):
            vals = pt.get("vals", {})
            if xN not in vals or yN not in vals:
                continue
            px, py = vals[xN], vals[yN]
            if X is not None and not (X.min() <= px <= X.max() and Y.min() <= py <= Y.max()):
                continue
            txt = "%s  %.0f °C" % (pt.get("label", "?"), pt.get("T", 0.0))
            w_px = 16 + len(txt) * (fs * 0.62)        # оценка ширины рамки
            key = (round(px, 9), round(py, 9))
            k = seen.get(key, 0); seen[key] = k + 1
            oy = k * (fs + 14)                        # каскад вверх при совпадении
            geom[i] = (px, py, LBL_OX, oy, w_px, txt)
        return geom

    def _draw_points(self, ax, X, Y, xN, yN, fs, TNR):
        """Маркер (точка) + рамка с буквой и пиковой T справа; крестик при наведении."""
        geom = self._point_geom(xN, yN, X, Y)
        for i, (px, py, ox, oy, w, txt) in geom.items():
            ax.plot(px, py, "o", ms=8, mfc="white", mec="k", mew=1.5, zorder=40)
            ax.annotate(txt, (px, py), textcoords="offset pixels", xytext=(ox, oy),
                        ha="left", va="center", fontsize=fs, fontweight="bold",
                        fontname=TNR, color="k", zorder=41,
                        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.4", alpha=0.95))
            if i == self._hover_idx:                  # крестик удаления справа над рамкой
                ax.annotate("✕", (px, py), textcoords="offset pixels",
                            xytext=(ox + w + 9, oy + 13), ha="center", va="center",
                            fontsize=max(8, fs - 1), fontweight="bold", color="#d11",
                            zorder=42, bbox=dict(boxstyle="circle,pad=0.10",
                                                 fc="white", ec="#d11"))

    def _hit_point(self, event):
        """Вернуть (idx, on_cross) точки под курсором или (None, False)."""
        if self._last_grid is None or self.view_var.get() != "2D":
            return None, False
        if event.x is None or event.y is None:
            return None, False
        xN, yN = self.xaxis_var.get(), self.yaxis_var.get()
        geom = self._point_geom(xN, yN)
        hit, on_cross = None, False
        for i, (px, py, ox, oy, w, txt) in geom.items():
            try:
                mx, my = self.ax.transData.transform((px, py))
            except Exception:
                continue
            if (event.x - mx) ** 2 + (event.y - my) ** 2 <= 12 ** 2:   # маркер
                hit = i
            if (mx + ox - 6 <= event.x <= mx + ox + w + 4
                    and my + oy - 13 <= event.y <= my + oy + 13):       # рамка с цифрой
                hit = i
            cx, cy = mx + ox + w + 9, my + oy + 13                      # крестик
            if (event.x - cx) ** 2 + (event.y - cy) ** 2 <= 12 ** 2:
                hit, on_cross = i, True
        return hit, on_cross

    def _on_pt_motion(self, event):
        if self._nav_active():
            return
        idx, _ = (None, False) if event.inaxes is not self.ax else self._hit_point(event)
        if idx != self._hover_idx:
            self._hover_idx = idx
            self._redraw_from_cache(idle=True)

    def _on_pt_click(self, event):
        if self._nav_active() or event.inaxes is not self.ax:
            return
        idx, on_cross = self._hit_point(event)
        if idx is None:
            return
        if event.dblclick:
            self._edit_point_label(idx)
        elif on_cross:
            self._delete_point(idx)

    def _delete_point(self, idx):
        if 0 <= idx < len(self._points):
            del self._points[idx]
            self._hover_idx = None
            self._redraw_from_cache()

    def _edit_point_label(self, idx):
        if not (0 <= idx < len(self._points)):
            return
        cur = self._points[idx]["label"]
        new = simpledialog.askstring(self.t("pt_edit_title"), self.t("pt_edit_msg"),
                                     initialvalue=cur, parent=self)
        if new and new.strip():
            self._points[idx]["label"] = new.strip()
            self._hover_idx = None
            self._redraw_from_cache()

    # ---------- построение ----------
    def _candidates(self):
        return AX_BY_MODE[self.input_mode]

    def _order(self):
        """Варьируемые («диапазонные») параметры — оси/матрица/регрессия идут по ним."""
        return [s for s in self._candidates() if self.vary[s].get() == "range"]

    def _resolve(self, p, vals, point=False):
        """vals: dict ВСЕХ параметров режима -> значение(скаляр/массив).
           point=True — расчёт в точке (можно учесть свою ширину валика w).
           Возвращает (omega, R_mm, H_mm, p_eff) для compute_T."""
        F_N = vals["F"] * 1e3                             # кН -> Н
        if self.input_mode == "kin":
            R = vals["D"] / 2.0
            vz, vx = vals["vz"], vals["vx"]
            # ширина валика = 2R; своя w — только в расчёте точки (галочка)
            wb = self._f("w_bead") if (point and self.beadw_on_var.get()) else 2.0 * R
            H = math.pi * R * R * (vz / vx) / wb         # мм
            pe = dict(p)
            pe["F"] = F_N
            pe["v"] = vx * 1e-3
            pe["v_z"] = vz * 1e-3
            pe["use_pe"] = True
            pe["use_feed"] = bool(self.use_feedsink_var.get())
            return vals["ω"], R, H, pe
        if self.input_mode == "shoulder":
            a = vals["a"]; rshoe = self._f("R_shoe")
            vz, vx, H = vals["vz"], vals["vx"], vals["H"]
            R_eff = np.minimum(a * a * vz / (2.0 * H * vx), rshoe)
            pe = dict(p)
            pe["F"] = F_N
            pe["v"] = vx * 1e-3
            pe["feedvol"] = (a * 1e-3) ** 2 * (vz * 1e-3)
            pe["use_pe"] = True
            pe["use_feed"] = bool(self.use_feedsink_var.get())
            if self.bore_var.get():
                pe["r_in"] = (a / math.sqrt(math.pi)) * 1e-3
            return vals["ω"], R_eff, H, pe
        return vals["ω"], vals["R"], vals["H"], p

    def _all_vals(self, override=None):
        """Полный словарь значений ВСЕХ кандидатов: рабочие значения (fix_vars),
           с переопределением осей/уровней через override."""
        vals = {}
        for s in self._candidates():
            try:
                vals[s] = float(self.fix_vars[s].get())
            except (ValueError, tk.TclError):
                vals[s] = 0.0
        if override:
            vals.update(override)
        return vals

    def _range(self, sym):
        return self._f(RANGE_KEYS[sym][0]), self._f(RANGE_KEYS[sym][1])

    def _ensure_axes(self):
        order = self._order()
        if len(order) < 1:
            return
        if self.xaxis_var.get() not in order:
            self.xaxis_var.set(order[0])
        if len(order) >= 2 and (self.yaxis_var.get() not in order
                                or self.yaxis_var.get() == self.xaxis_var.get()):
            self.yaxis_var.set(next(s for s in order if s != self.xaxis_var.get()))

    def _fixed_factors(self):
        self._ensure_axes()
        x, y = self.xaxis_var.get(), self.yaxis_var.get()
        return [s for s in self._order() if s not in (x, y)]

    def _on_axis_change(self):
        # X и Y не должны совпадать
        order = self._order()
        if self.xaxis_var.get() == self.yaxis_var.get():
            alt = [s for s in order if s != self.xaxis_var.get()]
            if alt:
                self.yaxis_var.set(alt[0])
        self._relayout()

    def build(self, *_):
        try:
            p = self._read_params()
            self._ensure_axes()
            order = self._order()
            if len(order) < 2:                 # для карты нужно ≥2 «диапазонных» параметра
                return
            xN, yN = self.xaxis_var.get(), self.yaxis_var.get()
            fixed = {s: float(self.fix_vars[s].get())
                     for s in self._candidates() if s not in (xN, yN)}
            rx, ry = self._range(xN), self._range(yN)
        except (ValueError, KeyError, tk.TclError):
            return
        if rx[1] <= rx[0] or ry[1] <= ry[0]:
            return

        is3d = self.view_var.get() == "3D"
        n = self.n3d if is3d else 140
        xv = np.linspace(*rx, n)
        yv = np.linspace(*ry, n)
        X, Y = np.meshgrid(xv, yv)
        vals = self._all_vals({xN: X, yN: Y})
        omega, R, H, pe = self._resolve(p, vals)
        T = compute_T(omega, R, H, pe, self.model_key)
        self._last_grid = (xN, yN, xv, yv, T, fixed)

        # сокращённая регрессия T_peak(x, y) — для наложения на карту и копии в LaTeX
        self._reduced_math = self._reduced_latex = None
        try:
            red = self._reduce_regression()
            if red:
                self._reduced_math, self._reduced_latex = red
        except Exception:
            pass

        Tmin, Tmax = self._window_C(p["T_solidus"])
        self.fig.clf()
        # журнальная аннотация (в поле графика, как в примере «Tool Radius R=5mm»)
        annot = "\n".join(self._plot_annot(s, v) for s, v in fixed.items())
        if is3d:
            self._draw_3d(X, Y, T, xN, yN, Tmin, Tmax, annot)
        else:
            self._draw_2d(X, Y, T, xN, yN, Tmin, Tmax, annot)
        self.canvas.draw()
        self._refresh_matrix()

    def _draw_2d(self, X, Y, T, xN, yN, Tmin, Tmax, annot):
        fs = self.plot_fs
        TNR = "Times New Roman"
        matplotlib.rcParams["mathtext.fontset"] = "stix"   # Times-подобные формулы
        ax = self.ax = self.fig.add_subplot(111)
        nlev = max(4, self._iv(self.nlev_var, 24))         # число градиентных цветов
        win_mode = self.colormode_var.get() == "window"
        if win_mode:
            cmap = matplotlib.colormaps["turbo"].with_extremes(under="white", over="white")
            levels = np.linspace(Tmin, Tmax, nlev)
            cf = ax.contourf(X, Y, T, levels=levels, cmap=cmap, extend="both")
        else:
            cf = ax.contourf(X, Y, T, levels=nlev, cmap="turbo")
        cb = self.fig.colorbar(cf, ax=ax, pad=self._fv(self.cbar_pad_var, self.cbar_pad))
        crot = 270 if self.cbar_flip_var.get() else 90        # надпись шкалы на 180°
        cb.set_label(r"Peak Temperature, $T$ ($^{\circ}$C)", fontsize=fs, fontname=TNR,
                     color="k", rotation=crot)
        # позиция надписи шкалы по X (в долях ширины шкалы): <0 — слева, >1 — справа
        cb.ax.yaxis.set_label_coords(self._fv(self.cbar_lblx_var, 3.5), 0.5)
        cb.ax.tick_params(labelsize=fs - 1, colors="k")
        for lab in cb.ax.get_yticklabels():
            lab.set_fontname(TNR)
        stroke = [mpe.withStroke(linewidth=2.4, foreground="white")]   # белая обводка (только пределы)
        # изотермы — чёрные тонкие линии с чёрными подписями (Times, без обводки)
        cs = ax.contour(X, Y, T, levels=10, colors="k", linewidths=0.5, alpha=0.6)
        for t in ax.clabel(cs, inline=True, fontsize=max(6, fs - 2), fmt="%.0f", colors="k"):
            t.set_fontname(TNR)
        # зелёная подсветка окна — по желанию (иначе границы видны лишь по линиям,
        # а цвет остаётся чистым градиентом без резкого зелёного перехода)
        if (not win_mode and self.winfill_var.get()
                and T.max() >= Tmin and T.min() <= Tmax):
            mask = np.where((T >= Tmin) & (T <= Tmax), 1.0, np.nan)
            ax.contourf(X, Y, mask, levels=[0.5, 1.5], colors=["#19d219"], alpha=0.30)
        _lo, _hi = self._wfracs()
        # Гомологическая температура T/T_s — отношение АБСОЛЮТНЫХ температур,
        # поэтому безразмерна и вопроса о единицах не возникает. В скобках —
        # соответствующее значение в °C, чтобы границу можно было читать прямо
        # с карты (шкала и изолинии тоже в °C).
        for lev, col, tag in [(Tmin, "#1565ff", r"$T/T_{s} = %g$" % _lo),
                              (Tmax, "#e8112d", r"$T/T_{s} = %g$" % _hi)]:
            try:
                c = ax.contour(X, Y, T, levels=[lev], colors=col, linewidths=2.0,
                               linestyles="--")
                for t in ax.clabel(c, fmt={lev: f"{tag} ({lev:.0f})"},
                                   fontsize=max(6, fs - 1),
                                   colors="k"):
                    t.set_fontname(TNR); t.set_path_effects(stroke)
            except Exception:
                pass
        self._draw_points(ax, X, Y, xN, yN, fs, TNR)
        # аннотация фикс. параметров (журнальный стиль, позиция настраивается)
        if annot:
            ax_, ay = self._fv(self.annotx_var, 0.97), self._fv(self.annoty_var, 0.96)
            ha = "right" if ax_ >= 0.5 else "left"
            va = "top" if ay >= 0.5 else "bottom"
            afs = max(4.0, fs * self._fv(self.annotscale_var, 1.0))   # масштаб рамки
            ax.text(ax_, ay, annot, transform=ax.transAxes, ha=ha, va=va,
                    fontsize=afs, fontname=TNR, color="k", zorder=50,
                    bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="0.5", alpha=1.0))
        lblpad = self._iv(self.lblpad_var, 6)
        tickpad = self._iv(self.tickpad_var, 3)
        ax.set_xlabel(self._plot_label(xN), fontsize=fs, fontname=TNR, color="k", labelpad=lblpad)
        ax.set_ylabel(self._plot_label(yN), fontsize=fs, fontname=TNR, color="k", labelpad=lblpad)
        # палочки внутрь на всех 4 сторонах (на параллельных осях тоже), цифры — низ/лево
        ax.tick_params(direction="in", labelsize=fs - 1, colors="k", pad=tickpad,
                       top=True, right=True, labeltop=False, labelright=False)
        ax.tick_params(which="minor", direction="in", top=True, right=True,
                       labeltop=False, labelright=False)
        # ось диаметра в радиусах (R = D/2), если включено
        if self.toolrad_var.get():
            from matplotlib.ticker import FuncFormatter
            half = FuncFormatter(lambda v, _p: ("%g" % (v / 2.0)))
            if xN == "D":
                ax.xaxis.set_major_formatter(half)
            if yN == "D":
                ax.yaxis.set_major_formatter(half)
        for lab in ax.get_xticklabels() + ax.get_yticklabels():
            lab.set_fontname(TNR); lab.set_color("k")
        aspect = self._aspect_value()                      # высота/ширина бокса (из W:H)
        if aspect > 0.05:
            try:
                ax.set_box_aspect(aspect)
            except Exception:
                pass
        self._overlay_regression(fs)

    def _overlay_regression(self, fs):
        """Сокращённое уравнение T_peak(x,y) внизу карты — по тумблеру."""
        show = self.showreg_var.get() and getattr(self, "_reduced_math", None)
        self.fig.tight_layout(rect=(0, 0.08, 1, 1) if show else (0, 0, 1, 1))
        if show:
            self.fig.text(0.5, 0.015, self._reduced_math, ha="center", va="bottom",
                          fontsize=max(7, fs - 2), family="Times New Roman", color="#111",
                          bbox=dict(boxstyle="round,pad=0.3", fc="#f6f6f6", ec="0.6"))

    def _draw_3d(self, X, Y, T, xN, yN, Tmin, Tmax, annot):
        fs = self.plot_fs
        TNR = "Times New Roman"
        matplotlib.rcParams["mathtext.fontset"] = "stix"
        ax = self.ax = self.fig.add_subplot(111, projection="3d")
        rc = self._iv(self.n3d_var, self.n3d)   # плотность сетки 3D (из панели стиля)
        if self.colormode_var.get() == "window":
            from matplotlib.colors import Normalize
            cmap = matplotlib.colormaps["turbo"].with_extremes(under="white", over="white")
            norm = Normalize(Tmin, Tmax, clip=False)
            surf = ax.plot_surface(X, Y, T, cmap=cmap, norm=norm, linewidth=0,
                                   antialiased=False, alpha=1.0, rcount=rc, ccount=rc)
        else:
            surf = ax.plot_surface(X, Y, T, cmap="turbo", linewidth=0,
                                   antialiased=False, alpha=1.0, rcount=rc, ccount=rc)
        cb = self.fig.colorbar(surf, ax=ax, pad=self._fv(self.cbar_pad_var, self.cbar_pad) + 0.04,
                               shrink=0.6)
        crot = 270 if self.cbar_flip_var.get() else 90
        cb.set_label(r"Peak Temperature, $T$ ($^{\circ}$C)", fontsize=fs, fontname=TNR,
                     color="k", rotation=crot)
        cb.ax.yaxis.set_label_coords(self._fv(self.cbar_lblx_var, 3.5), 0.5)
        cb.ax.tick_params(labelsize=fs - 1, colors="k")
        for lab in cb.ax.get_yticklabels():
            lab.set_fontname(TNR)
        xp = np.array([[X.min(), X.max()], [X.min(), X.max()]])
        yp = np.array([[Y.min(), Y.min()], [Y.max(), Y.max()]])
        if T.min() <= Tmin <= T.max():
            ax.plot_surface(xp, yp, np.full_like(xp, Tmin), color="#1565ff", alpha=0.18)
        if T.min() <= Tmax <= T.max():
            ax.plot_surface(xp, yp, np.full_like(xp, Tmax), color="#e8112d", alpha=0.18)
        ax.set_xlabel(self._plot_label(xN), fontsize=fs - 1, fontname=TNR, color="k")
        ax.set_ylabel(self._plot_label(yN), fontsize=fs - 1, fontname=TNR, color="k")
        ax.set_zlabel(r"Peak Temperature, $T$ ($^{\circ}$C)", fontsize=fs - 1, fontname=TNR, color="k")
        ax.tick_params(labelsize=fs - 2, colors="k")
        if self.toolrad_var.get():
            from matplotlib.ticker import FuncFormatter
            half = FuncFormatter(lambda v, _p: ("%g" % (v / 2.0)))
            if xN == "D":
                ax.xaxis.set_major_formatter(half)
            if yN == "D":
                ax.yaxis.set_major_formatter(half)
        for lab in (ax.get_xticklabels() + ax.get_yticklabels() + ax.get_zticklabels()):
            lab.set_fontname(TNR); lab.set_color("k")
        if annot:
            axx, ayy = self._fv(self.annotx_var, 0.97), self._fv(self.annoty_var, 0.96)
            ha = "right" if axx >= 0.5 else "left"
            va = "top" if ayy >= 0.5 else "bottom"
            afs = max(4.0, fs * self._fv(self.annotscale_var, 1.0))
            ax.text2D(axx, ayy, annot, transform=ax.transAxes, ha=ha, va=va,
                      fontsize=afs, fontname=TNR, color="k")
        ax.view_init(elev=self._iv(self.elev_var, 28), azim=self._iv(self.azim_var, -130))
        if self.showreg_var.get() and getattr(self, "_reduced_math", None):
            self.fig.text(0.5, 0.015, self._reduced_math, ha="center", va="bottom",
                          fontsize=max(7, fs - 2), family=TNR, color="#111",
                          bbox=dict(boxstyle="round,pad=0.3", fc="#f6f6f6", ec="0.6"))

    # ---------- регрессия: общий список членов и LaTeX ----------
    @staticmethod
    def _poly_terms(c0, lin, quad, inter, syms):
        """Список (коэф, символ) всех членов полинома по N переменным."""
        N = len(syms)
        terms = [(c0, "")]
        terms += [(lin[j], syms[j]) for j in range(N)]
        terms += [(quad[j], syms[j] + "^{2}") for j in range(N)]
        pairs = list(itertools.combinations(range(N), 2))
        terms += [(inter[i], syms[a] + r"\," + syms[b]) for i, (a, b) in enumerate(pairs)]
        return terms

    @staticmethod
    def _poly_body(terms):
        """Один LaTeX/mathtext-фрагмент правой части (без обрамления $...$)."""
        out = ""
        first = True
        for coef, sym in terms:
            if coef == 0:
                continue
            sign = "-" if coef < 0 else "+"
            val = f"{abs(coef):g}"
            body = (val + r"\," + sym) if sym else val
            if first:
                out += ("-" + body) if sign == "-" else body
                first = False
            else:
                out += " " + sign + " " + body
        return out or "0"

    def _regression_latex(self, c0, lin, quad, inter, syms, args=None):
        """Готовое к вставке уравнение LaTeX (environment equation)."""
        body = self._poly_body(self._poly_terms(c0, lin, quad, inter, syms))
        lhs = r"T_{\mathrm{peak}}"
        if args:
            lhs += "(" + ",\\ ".join(args) + ")"
        return ("\\begin{equation}\n  " + lhs + " = " + body + "\n\\end{equation}")

    def _reduce_regression(self):
        """Свести N-факторную регрессию к T_peak(x, y): фикс-факторы -> числа.
           Возвращает (math, latex) или None."""
        fit = self._fit_regression()
        if not fit:
            return None
        c0, lin, quad, inter, order = fit
        xN, yN = self.xaxis_var.get(), self.yaxis_var.get()
        try:
            fv = {s: float(self.fix_vars[s].get()) for s in order if s not in (xN, yN)}
        except (ValueError, tk.TclError):
            return None
        N = len(order)
        c0r = c0
        cx = cy = cxx = cyy = cxy = 0.0
        for j, s in enumerate(order):                 # линейные
            if s == xN:
                cx += lin[j]
            elif s == yN:
                cy += lin[j]
            else:
                c0r += lin[j] * fv[s]
        for j, s in enumerate(order):                 # квадратичные
            if s == xN:
                cxx += quad[j]
            elif s == yN:
                cyy += quad[j]
            else:
                c0r += quad[j] * fv[s] ** 2
        pairs = list(itertools.combinations(range(N), 2))
        for w, (a, b) in zip(inter, pairs):           # взаимодействия
            sa, sb = order[a], order[b]
            ax_ = sa in (xN, yN)
            bx_ = sb in (xN, yN)
            if ax_ and bx_:                           # один — x, другой — y
                cxy += w
            elif ax_:                                 # sb фиксирован
                (cx, cy) = (cx + w * fv[sb], cy) if sa == xN else (cx, cy + w * fv[sb])
            elif bx_:                                 # sa фиксирован
                (cx, cy) = (cx + w * fv[sa], cy) if sb == xN else (cx, cy + w * fv[sa])
            else:                                     # оба фиксированы
                c0r += w * fv[sa] * fv[sb]
        r = lambda v: round(float(v), 6)
        c0r, cx, cy, cxx, cyy, cxy = map(r, (c0r, cx, cy, cxx, cyy, cxy))
        sx, sy = self.AX_MATH[xN], self.AX_MATH[yN]
        terms = [(c0r, ""), (cx, sx), (cy, sy),
                 (cxx, sx + "^{2}"), (cyy, sy + "^{2}"), (cxy, sx + r"\," + sy)]
        body = self._poly_body(terms)
        math = r"$T_{\mathrm{peak}}(%s,\,%s)=%s$" % (sx, sy, body)
        latex = ("\\begin{equation}\n  T_{\\mathrm{peak}}(%s,\\ %s) = %s\n\\end{equation}"
                 % (sx, sy, body))
        return math, latex

    def _copy_clip(self, text, msg=None):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
            if msg:
                messagebox.showinfo("LaTeX", msg)
        except tk.TclError:
            pass

    def _copy_reduced_latex(self):
        """Скопировать сокращённое уравнение T_peak(x,y) в LaTeX."""
        latex = getattr(self, "_reduced_latex", None)
        if not latex:
            red = self._reduce_regression()
            latex = red[1] if red else None
        if latex:
            self._copy_clip(latex, self.t("copied_latex"))
        else:
            messagebox.showwarning(self.t("no_data"), self.t("no_data_msg"))

    def _copy_full_latex(self):
        """Скопировать полное регрессионное уравнение (вкладка «Формулы») в LaTeX."""
        latex = getattr(self, "_full_reg_latex", None)
        if latex:
            self._copy_clip(latex, self.t("copied_latex"))
        else:
            messagebox.showwarning(self.t("no_data"), self.t("no_data_msg"))


    # ---------- About / Settings ----------
    def show_about(self):
        win = tk.Toplevel(self)
        win.title(self.t("menu_about"))
        win.transient(self); win.resizable(False, False)
        ttk.Label(win, text=ABOUT_TEXT.get(self.lang, ABOUT_TEXT["en"]), justify="left",
                  font=(self.ui_family, self.ui_size), padding=18).pack()
        br = ttk.Frame(win); br.pack(pady=(0, 14))
        ttk.Button(br, text=self.t("btn_guide"), style="Accent.TButton",
                   command=lambda: (win.destroy(), self.show_guide())).pack(side="left", padx=4)
        ttk.Button(br, text="OK", command=win.destroy).pack(side="left", padx=4)
        win.grab_set()

    def show_guide(self, *_):
        """Окно с подробным руководством пользователя (прокручиваемый текст)."""
        win = tk.Toplevel(self)
        win.title(self.t("menu_guide") + " — " + APP_NAME)
        win.transient(self); win.geometry("780x620")
        frm = ttk.Frame(win, padding=6); frm.pack(fill="both", expand=True)
        txt = tk.Text(frm, wrap="word", font=(self.ui_family, self.ui_size),
                      padx=10, pady=8, bg="white", relief="flat")
        vsb = ttk.Scrollbar(frm, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", GUIDE_TEXT.get(self.lang, GUIDE_TEXT["en"]))
        txt.configure(state="disabled")
        txt.bind("<MouseWheel>", lambda e: txt.yview_scroll(int(-e.delta / 120), "units"))
        ttk.Button(win, text="OK", command=win.destroy).pack(pady=(0, 10))

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title(self.t("set_title"))
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        lang_var = tk.StringVar(value=dict(LANGS)[self.lang])
        uifam_var = tk.StringVar(value=self.ui_family)
        uisize_var = tk.IntVar(value=self.ui_size)
        gfam_var = tk.StringVar(value=self.plot_family)
        gsize_var = tk.IntVar(value=self.plot_fs)
        cbpad_var = tk.DoubleVar(value=self.cbar_pad)
        n3d_var = tk.IntVar(value=self.n3d)

        rows = [
            (self.t("set_lang"),
             ttk.Combobox(frm, textvariable=lang_var, state="readonly",
                          values=[n for _, n in LANGS], width=22)),
            (self.t("set_uifont"),
             ttk.Combobox(frm, textvariable=uifam_var, state="readonly",
                          values=FONT_FAMILIES, width=22)),
            (self.t("set_uisize"),
             ttk.Spinbox(frm, from_=8, to=20, textvariable=uisize_var, width=8)),
            (self.t("set_gfont"),
             ttk.Combobox(frm, textvariable=gfam_var, state="readonly",
                          values=FONT_FAMILIES, width=22)),
            (self.t("set_gsize"),
             ttk.Spinbox(frm, from_=6, to=20, textvariable=gsize_var, width=8)),
            (self.t("set_cbarpad"),
             ttk.Spinbox(frm, from_=0.0, to=0.4, increment=0.02, format="%.2f",
                         textvariable=cbpad_var, width=8)),
            (self.t("set_n3d"),
             ttk.Spinbox(frm, from_=20, to=100, increment=4, textvariable=n3d_var, width=8)),
        ]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(frm, text=label, anchor="w").grid(row=i, column=0, sticky="w",
                                                        padx=(0, 12), pady=5)
            widget.grid(row=i, column=1, sticky="ew", pady=5)

        btns = ttk.Frame(frm)
        btns.grid(row=len(rows), column=0, columnspan=2, sticky="e", pady=(16, 0))

        def apply_settings():
            name2code = {n: c for c, n in LANGS}
            self.lang = name2code.get(lang_var.get(), self.lang)
            self.ui_family = uifam_var.get()
            self.ui_size = int(uisize_var.get())
            self.plot_family = gfam_var.get()
            self.plot_fs = int(gsize_var.get())
            self.cbar_pad = float(cbpad_var.get())
            self.cbar_pad_var.set(self.cbar_pad)   # синхрон с ползунком у графика
            self.n3d = int(n3d_var.get()); self.n3d_var.set(self.n3d)
            win.destroy()
            self._relayout()

        ttk.Button(btns, text=self.t("set_ok"), command=apply_settings).pack(side="right", padx=4)
        ttk.Button(btns, text=self.t("set_cancel"), command=win.destroy).pack(side="right")
        self._lock_wheel(win)            # колесо не меняет значения в настройках
        win.update_idletasks()
        win.minsize(380, win.winfo_reqheight())
        win.grab_set()
        win.lift()

    # ---------- проекты ----------
    def _project_data(self):
        return dict(
            fields={k: v.get() for k, v in self._fields.items()},
            preset=self.preset_var.get(), model_key=self.model_key,
            view=self.view_var.get(), xaxis=self.xaxis_var.get(), yaxis=self.yaxis_var.get(),
            fix={s: float(v.get()) for s, v in self.fix_vars.items()},
            colormode=self.colormode_var.get(), use_pe=bool(self.use_pe_var.get()),
            tdep=bool(self.tdep_var.get()),
            input_mode=self.input_mode, substrate=self.substrate_var.get(),
            sub_same=bool(self.sub_same_var.get()),
            shoe=self.shoe_var.get(), bore=bool(self.bore_var.get()),
            lang=self.lang, ui_family=self.ui_family, ui_size=self.ui_size,
            plot_family=self.plot_family, plot_fs=self.plot_fs,
            cbar_pad=self._fv(self.cbar_pad_var, self.cbar_pad),
            n3d=self.n3d,
            lblpad=self._iv(self.lblpad_var, 6), tickpad=self._iv(self.tickpad_var, 3),
            nlev=self._iv(self.nlev_var, 24), aspect=self._aspect_value(),
            aspw=self._fv(self.aspw_var, 4.0), asph=self._fv(self.asph_var, 3.0),
            annotx=self._fv(self.annotx_var, 0.97), annoty=self._fv(self.annoty_var, 0.96),
            toolrad=bool(self.toolrad_var.get()),
            cbar_flip=bool(self.cbar_flip_var.get()),
            cbar_lblx=self._fv(self.cbar_lblx_var, 3.5),
            annotscale=self._fv(self.annotscale_var, 1.0),
            wlo=self._fv(self.wlo_var, 0.6), whi=self._fv(self.whi_var, 0.9),
            winfill=bool(self.winfill_var.get()), showreg=bool(self.showreg_var.get()),
            points=self._points,
            vary={s: v.get() for s, v in self.vary.items()},
            mu_tdep=bool(self.mu_tdep_var.get()),
            mu_pair=self.mu_pair_var.get(), use_feedsink=bool(self.use_feedsink_var.get()),
            style_views=self._style_views_snapshot(),   # раздельные стили 2D/3D
        )

    def _style_views_snapshot(self):
        """Снимок настроек оформления обоих видов (активный синхронизирован из полей)."""
        try:
            self._save_style(self.view_var.get())
        except Exception:
            pass
        return {v: dict(d) for v, d in self._style_store.items()}

    def _write_project(self, path):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._project_data(), fh, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror(self.t("err"), str(e))
            return False
        self._project_path = path
        self._update_title()
        self._mark_saved()
        return True

    # ---------- несохранённые изменения ----------
    def _mark_saved(self):
        try:
            self._saved_snapshot = json.dumps(self._project_data(), ensure_ascii=False,
                                              sort_keys=True)
        except Exception:
            self._saved_snapshot = None

    def _is_dirty(self):
        snap = getattr(self, "_saved_snapshot", None)
        if snap is None:
            return False
        try:
            return json.dumps(self._project_data(), ensure_ascii=False, sort_keys=True) != snap
        except Exception:
            return False

    def _maybe_save(self):
        """Если есть несохранённые правки — спросить. True = можно продолжать,
           False = пользователь отменил действие."""
        if not self._is_dirty():
            return True
        r = messagebox.askyesnocancel(self.t("ask_save_title"), self.t("ask_save_msg"))
        if r is None:
            return False
        if r:
            self.save_project()
            if self._is_dirty():        # сохранение отменили (Save As)
                return False
        return True

    def new_project(self, *_):
        if not self._maybe_save():
            return
        self._init_vars()
        self._project_path = None
        self._relayout()
        self._mark_saved()

    def _on_close(self, *_):
        if self._maybe_save():
            self.destroy()

    def save_project(self, *_):
        """Сохранить: пересохранить текущий проект (без диалога), иначе — как «Сохранить как…»."""
        if self._project_path:
            if self._write_project(self._project_path):
                messagebox.showinfo(self.t("saved"), self._project_path)
        else:
            self.save_project_as()

    def save_project_as(self, *_):
        path = filedialog.asksaveasfilename(
            defaultextension=".afsd",
            filetypes=[("AFSD project", "*.afsd"), ("JSON", "*.json")],
            initialfile=os.path.basename(self._project_path) if self._project_path else "project.afsd")
        if not path:
            return
        if self._write_project(path):
            messagebox.showinfo(self.t("saved"), path)

    def open_project(self, *_):
        if not self._maybe_save():
            return
        path = filedialog.askopenfilename(
            filetypes=[("AFSD project", "*.afsd"), ("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            messagebox.showerror(self.t("err"), str(e))
            return
        for k, v in data.get("fields", {}).items():
            if k in self._fields:
                self._fields[k].set(v)
        self.preset_var.set(data.get("preset", DEFAULT_PRESET))
        self.model_key = data.get("model_key", "phys")
        self.view_var.set(data.get("view", "2D"))
        self.colormode_var.set(data.get("colormode", "full"))
        self.use_pe_var.set(data.get("use_pe", False))
        self.tdep_var.set(data.get("tdep", False))
        self.input_mode = data.get("input_mode", "kin")
        if self.input_mode not in AX_BY_MODE:     # старые проекты с режимом "H"
            self.input_mode = "kin"
        self.input_mode_var.set(self.input_mode)
        # подложка: новый формат (sub_same + материал) и совместимость со старым (SUB_SAME)
        sub = data.get("substrate", SUB_SAME)
        if "sub_same" in data:
            self.sub_same_var.set(bool(data.get("sub_same")))
            self.substrate_var.set(sub if sub != SUB_SAME and sub in self.materials else DEFAULT_PRESET)
        else:
            self.sub_same_var.set(sub == SUB_SAME)
            self.substrate_var.set(sub if sub != SUB_SAME and sub in self.materials else DEFAULT_PRESET)
        self.shoe_var.set(data.get("shoe", SHOE_NONE))
        self.bore_var.set(data.get("bore", False))
        self.xaxis_var.set(data.get("xaxis", "ω"))
        self.yaxis_var.set(data.get("yaxis", "H"))
        for s, v in data.get("fix", {}).items():
            if s in self.fix_vars:
                self.fix_vars[s].set(v)
        self.lang = data.get("lang", self.lang)
        self.ui_family = data.get("ui_family", self.ui_family)
        self.ui_size = data.get("ui_size", self.ui_size)
        self.plot_family = data.get("plot_family", self.plot_family)
        self.plot_fs = data.get("plot_fs", self.plot_fs)
        self.cbar_pad = data.get("cbar_pad", self.cbar_pad)
        self.n3d = data.get("n3d", self.n3d)
        self.plotfs_var.set(self.plot_fs)
        self.lblpad_var.set(data.get("lblpad", 6))
        self.tickpad_var.set(data.get("tickpad", 3))
        self.nlev_var.set(data.get("nlev", 24))
        if "aspw" in data and "asph" in data:
            self.aspw_var.set(data.get("aspw", 4.0))
            self.asph_var.set(data.get("asph", 3.0))
        else:                                  # старый проект: только число H/W
            asp = data.get("aspect", 0.75)
            self.aspw_var.set(1.0); self.asph_var.set(round(asp, 4) if asp > 0 else 0.75)
        self.aspect_var.set(round(self._aspect_value(), 4))
        self.annotx_var.set(data.get("annotx", 0.97))
        self.annoty_var.set(data.get("annoty", 0.96))
        self.toolrad_var.set(data.get("toolrad", False))
        self.cbar_flip_var.set(data.get("cbar_flip", False))
        self.cbar_lblx_var.set(data.get("cbar_lblx", 3.5))
        self.cbar_pad_var.set(self.cbar_pad)
        self.annotscale_var.set(data.get("annotscale", 1.0))
        self.wlo_var.set(data.get("wlo", 0.6))
        self.whi_var.set(data.get("whi", 0.9))
        # раздельные стили 2D/3D: восстановить хранилище и применить активный вид
        sv = data.get("style_views")
        if isinstance(sv, dict):
            for view in ("2D", "3D"):
                if isinstance(sv.get(view), dict):
                    self._style_store[view].update(sv[view])
        self._prev_view = self.view_var.get()
        self._load_style(self._prev_view)
        pts = data.get("points", [])
        self._points = [dict(label=str(p.get("label", "?")),
                             vals={k: float(v) for k, v in p.get("vals", {}).items()},
                             T=float(p.get("T", 0.0))) for p in pts if isinstance(p, dict)]
        self._hover_idx = None
        self.winfill_var.set(data.get("winfill", False))
        self.showreg_var.set(data.get("showreg", False))
        for s, mode in data.get("vary", {}).items():
            if s in self.vary and mode in ("range", "fixed"):
                self.vary[s].set(mode)
        self.mu_tdep_var.set(data.get("mu_tdep", False))
        self.mu_pair_var.set(data.get("mu_pair", MU_PAIR_NONE))
        self.use_feedsink_var.set(data.get("use_feedsink", True))
        self._project_path = path
        self._update_title()
        self._relayout()
        self._mark_saved()

    # ---------- экспорт ----------
    def _save_figure(self, ext, *_):
        """Сохранить текущий график (со всеми надписями) в указанном формате.
           pdf/svg — вектор; png — растр (dpi=300)."""
        types = {"png": ("PNG", "*.png"), "pdf": ("PDF (вектор)", "*.pdf"),
                 "svg": ("SVG (вектор)", "*.svg")}
        ft = [types[ext]] + [types[e] for e in ("png", "pdf", "svg") if e != ext]
        path = filedialog.asksaveasfilename(defaultextension="." + ext, filetypes=ft,
                                            initialfile="afsd_map." + ext)
        if not path:
            return
        try:
            self.fig.savefig(path, dpi=300, bbox_inches="tight")
        except Exception as e:
            messagebox.showerror(self.t("err"), str(e))
            return
        messagebox.showinfo(self.t("saved"), path)

    def save_png(self, *_):
        self._save_figure("png")

    def save_pdf(self, *_):
        self._save_figure("pdf")

    def save_svg(self, *_):
        self._save_figure("svg")

    def export_csv(self, *_):
        if self._last_grid is None:
            messagebox.showwarning(self.t("no_data"), self.t("no_data_msg"))
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="afsd_grid.csv")
        if not path:
            return
        xN, yN, xv, yv, T, fixed = self._last_grid
        fixhdr = "; ".join(f"{s}={v:g}" for s, v in fixed.items())
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# fixed: {fixhdr}\n{xN},{yN},Tpeak_C,Tpeak_K\n")
            for j, yy in enumerate(yv):
                for i, xx in enumerate(xv):
                    fh.write(f"{xx:.4f},{yy:.4f},{T[j, i]:.3f},{c_to_k(T[j, i]):.3f}\n")
        messagebox.showinfo(self.t("saved"), path)


if __name__ == "__main__":
    App().mainloop()
