# -*- coding: utf-8 -*-
"""
AFSD Predictor — расчётное ядро
===============================
Физическая модель, база материалов и строки перевода. Модуль не зависит
от GUI: сюда не импортируется ни tkinter, ни Qt, ни matplotlib. Любой
интерфейс (Tk, Qt) строится поверх этого модуля.

Модель (статья Y. Dvirnyk et al., Next Materials 11 (2026) 101778):
  sigma_y(T) = sigma_ref * [1 - ((T - T0)/(T_ref - T0))^m]      (ур. 13/14)
  tau_y      = sigma_y / sqrt(3)                                 (Мизес)
  Q_total    = (2/3) * pi * omega * tau_y * (R^3 + 3 R^2 H)      (ур. 4)
  T_peak     = T0 + Q_total / (4 k R)                            (ур. 10)
T_peak — самосогласованная итерация. Окно: 0.6 Ts <= T_peak <= 0.9 Ts (ур. 11)
"""

import os
import sys
import json
import math
import itertools
import numpy as np

SQRT3 = math.sqrt(3.0)
ORDER = ["ω", "R", "H"]
# оси по процессу: shoulderless (пруток, v↓,v→,D) и shouldered (MELD).
# Полный набор кандидатов-параметров на режим. У каждого свой тумблер
# «диапазон/одно число» (self.vary): в матрицу/оси идут только «диапазонные».
AX_BY_MODE = {"kin": ["ω", "vz", "vx", "D", "F"],
              "shoulder": ["ω", "vz", "vx", "H", "a", "F"]}
RANGE_KEYS = {"ω": ("w_min", "w_max"), "R": ("R_min", "R_max"), "H": ("H_min", "H_max"),
              "vz": ("vz_min", "vz_max"), "vx": ("vx_min", "vx_max"), "D": ("D_min", "D_max"),
              "a": ("a_min", "a_max"), "F": ("F_min", "F_max")}
PT_KEY = {"ω": "pt_w", "R": "pt_R", "H": "pt_H", "vz": "pt_vz", "vx": "pt_vx",
          "D": "pt_D", "a": "pt_a", "F": "pt_F"}
AX_LABEL_KEY = {"ω": "ax_w", "R": "ax_r", "H": "ax_h", "vz": "ax_vz", "vx": "ax_vx",
                "D": "ax_D", "a": "ax_a", "F": "ax_F"}
AX_UNIT_KEY = {"ω": "unit_rpm", "R": "unit_mm", "H": "unit_mm",
               "vz": "unit_mms", "vx": "unit_mms", "D": "unit_mm", "a": "unit_mm",
               "F": "unit_kN"}
MODEL_ORDER = ["phys", "emp", "poly"]

# Температурозависимый коэффициент трения μ(T) для контактных пар (T в °C).
# НОМИНАЛЬНЫЕ значения (μ убывает с разогревом контакта) — ориентир для пар из
# валидационных экспериментов; правьте под свои данные. Линейная интерполяция,
# вне диапазона — крайнее значение. Используются при включённой галочке μ(T).
MU_PAIR_NONE = "(константа)"
MU_TABLES = {
    "Al–steel (Эксп.7)":  [[25, 0.55], [200, 0.50], [400, 0.42], [560, 0.33]],
    "Al–Al (Эксп.3,8)":   [[25, 0.50], [200, 0.45], [400, 0.38], [580, 0.30]],
    "Al–Ti6Al4V (Эксп.1,2)": [[25, 0.50], [200, 0.45], [400, 0.40], [580, 0.33]],
    "steel–steel (Эксп.4,10)": [[25, 0.50], [400, 0.45], [800, 0.38], [1400, 0.30]],
    "Mg–Mg (Эксп.9)":     [[25, 0.50], [200, 0.45], [400, 0.40], [620, 0.32]],
}
LANGS = [("en", "English"), ("uk", "Українська"), ("ru", "Русский"), ("zh", "中文")]
FONT_FAMILIES = ["Segoe UI", "Arial", "Tahoma", "Calibri", "Verdana",
                 "Times New Roman", "Consolas", "DejaVu Sans"]

# ----------------------------------------------------------------------------
#  База сплавов.  Значения C_emp/poly заданы только для AA6061/AZ31B (статья);
#  для остальных — номинальные литературные параметры типа Джонсона–Кука
#  (σ_ref ≈ опорный предел текучести, T_ref ≈ ликвидус), их следует проверять.
# ----------------------------------------------------------------------------
PRESETS = {
    # --- магний ---
    "AZ31B (Mg)": dict(sigma_ref=220.0, T_ref=630.0, m=0.95, k=98.0,
                       T_solidus=605.0, T0=25.0, rho=1770.0, cp=1050.0, C_emp=47.6,
                       poly=dict(c0=-284.98, w=0.6690, R=108.40, H=96.11,
                                 w2=-0.00027, R2=-4.7911, H2=-5.7506,
                                 wR=-0.01758, wH=-0.01345, RH=-5.8476)),
    "AZ91D (Mg)": dict(sigma_ref=160.0, T_ref=595.0, m=1.0, k=72.0,
                       T_solidus=468.0, T0=25.0, rho=1810.0, cp=1050.0, C_emp=None, poly=None),
    # --- алюминий ---
    "AA6061-T6 (Al)": dict(sigma_ref=276.0, T_ref=650.0, m=1.34, k=167.0,
                           T_solidus=582.0, T0=25.0, rho=2700.0, cp=896.0, C_emp=29.1,
                           poly=dict(c0=-339.25, w=0.7316, R=119.39, H=91.41,
                                     w2=-0.00029, R2=-5.2148, H2=0.0,
                                     wR=-0.02, wH=-0.01377, RH=-6.5007)),
    "AA2024-T3 (Al)": dict(sigma_ref=369.0, T_ref=638.0, m=1.0, k=121.0,
                           T_solidus=502.0, T0=25.0, rho=2780.0, cp=875.0, C_emp=None, poly=None),
    "AA7075-T6 (Al)": dict(sigma_ref=473.0, T_ref=635.0, m=1.34, k=130.0,
                           T_solidus=477.0, T0=25.0, rho=2810.0, cp=960.0, C_emp=None, poly=None),
    "AA5083-H116 (Al)": dict(sigma_ref=228.0, T_ref=638.0, m=1.0, k=117.0,
                             T_solidus=574.0, T0=25.0, rho=2660.0, cp=900.0, C_emp=None, poly=None),
    "AA1100 (Al)": dict(sigma_ref=110.0, T_ref=657.0, m=1.0, k=222.0,
                        T_solidus=643.0, T0=25.0, rho=2710.0, cp=904.0, C_emp=None, poly=None),
    # --- титан ---
    "Ti-6Al-4V (Grade 5)": dict(sigma_ref=1098.0, T_ref=1660.0, m=1.1, k=6.7,
                                T_solidus=1604.0, T0=25.0, rho=4430.0, cp=526.0, C_emp=None, poly=None),
    "CP-Ti (Grade 2)": dict(sigma_ref=380.0, T_ref=1670.0, m=1.0, k=17.0,
                            T_solidus=1665.0, T0=25.0, rho=4510.0, cp=523.0, C_emp=None, poly=None),
    # --- никелевые (инконели) ---
    "Inconel 718 (Ni)": dict(sigma_ref=1241.0, T_ref=1336.0, m=1.3, k=11.4,
                             T_solidus=1260.0, T0=25.0, rho=8190.0, cp=435.0, C_emp=None, poly=None),
    "Inconel 625 (Ni)": dict(sigma_ref=600.0, T_ref=1350.0, m=1.3, k=9.8,
                             T_solidus=1290.0, T0=25.0, rho=8440.0, cp=410.0, C_emp=None, poly=None),
    "Inconel 600 (Ni)": dict(sigma_ref=310.0, T_ref=1413.0, m=1.3, k=14.9,
                             T_solidus=1354.0, T0=25.0, rho=8470.0, cp=444.0, C_emp=None, poly=None),
    # --- стали ---
    "AISI 1045 (steel)": dict(sigma_ref=553.0, T_ref=1460.0, m=1.0, k=49.8,
                              T_solidus=1430.0, T0=25.0, rho=7850.0, cp=486.0, C_emp=None, poly=None),
    "AISI 4340 (steel)": dict(sigma_ref=792.0, T_ref=1520.0, m=1.03, k=44.5,
                              T_solidus=1427.0, T0=25.0, rho=7850.0, cp=475.0, C_emp=None, poly=None),
    "AISI 316L (steel)": dict(sigma_ref=305.0, T_ref=1400.0, m=0.65, k=16.3,
                              T_solidus=1375.0, T0=25.0, rho=8000.0, cp=500.0, C_emp=None, poly=None),
    "AISI 304 (steel)": dict(sigma_ref=310.0, T_ref=1450.0, m=1.0, k=16.2,
                             T_solidus=1400.0, T0=25.0, rho=8000.0, cp=500.0, C_emp=None, poly=None),
    "A36 (mild steel)": dict(sigma_ref=250.0, T_ref=1480.0, m=1.0, k=52.0,
                             T_solidus=1425.0, T0=25.0, rho=7850.0, cp=486.0, C_emp=None, poly=None),
    # --- медь ---
    "Cu OFHC": dict(sigma_ref=90.0, T_ref=1083.0, m=1.09, k=386.0,
                    T_solidus=1083.0, T0=25.0, rho=8960.0, cp=385.0, C_emp=None, poly=None),
    # --- свой ---
    "Custom": dict(sigma_ref=276.0, T_ref=650.0, m=1.0, k=150.0,
                   T_solidus=580.0, T0=25.0, rho=2700.0, cp=900.0, C_emp=None, poly=None),
}
DEFAULT_PRESET = "AA6061-T6 (Al)"
SUB_SAME = "(= материал прутка)"   # подложка как у прутка
SHOE_NONE = "(без отвода вверх)"   # шайба не отводит тепло (k2=0)

# ----------------------------------------------------------------------------
#  Таблицы температурозависимых свойств: kt = k(T) [Вт/м·К], cpt = cₚ(T) [Дж/кг·К].
#  T в °C. Значения — литературные приближения, проверяйте перед ответств. расчётами.
#  Линейная интерполяция между точками; вне диапазона — крайнее значение.
# ----------------------------------------------------------------------------
PROP_TABLES = {
    "AA6061-T6 (Al)": dict(
        kt=[[25, 167], [100, 172], [200, 177], [300, 184], [400, 190], [500, 194], [582, 198]],
        cpt=[[25, 896], [100, 940], [200, 978], [300, 1004], [400, 1052], [500, 1100], [582, 1140]]),
    "AA2024-T3 (Al)": dict(
        kt=[[25, 121], [100, 142], [200, 163], [300, 177], [400, 189], [502, 193]],
        cpt=[[25, 875], [100, 920], [200, 963], [300, 1000], [400, 1047], [502, 1080]]),
    "AA7075-T6 (Al)": dict(
        kt=[[25, 130], [100, 150], [200, 168], [300, 177], [400, 182], [477, 185]],
        cpt=[[25, 960], [100, 1000], [200, 1050], [300, 1100], [400, 1150], [477, 1180]]),
    "AA5083-H116 (Al)": dict(
        kt=[[25, 117], [100, 125], [200, 134], [300, 142], [400, 150], [574, 160]],
        cpt=[[25, 900], [100, 940], [200, 980], [300, 1020], [400, 1060], [574, 1120]]),
    "AA1100 (Al)": dict(
        kt=[[25, 222], [100, 222], [200, 224], [300, 226], [400, 228], [643, 232]],
        cpt=[[25, 904], [100, 944], [200, 980], [300, 1010], [400, 1050], [643, 1130]]),
    "AZ31B (Mg)": dict(
        kt=[[25, 96], [100, 100], [200, 104], [300, 108], [400, 112], [500, 116], [605, 120]],
        cpt=[[25, 1000], [100, 1040], [200, 1080], [300, 1130], [400, 1180], [500, 1230], [605, 1280]]),
    "AZ91D (Mg)": dict(
        kt=[[25, 72], [100, 78], [200, 84], [300, 90], [400, 96], [468, 100]],
        cpt=[[25, 1020], [100, 1060], [200, 1100], [300, 1150], [400, 1200], [468, 1240]]),
    "Ti-6Al-4V (Grade 5)": dict(
        kt=[[25, 6.7], [300, 9.8], [500, 11.8], [700, 13.4], [900, 15.5], [1100, 19], [1600, 24]],
        cpt=[[25, 526], [300, 565], [500, 606], [700, 651], [900, 700], [1100, 750], [1600, 830]]),
    "CP-Ti (Grade 2)": dict(
        kt=[[25, 17], [300, 18.5], [500, 19.5], [700, 20.5], [900, 21.5], [1665, 24]],
        cpt=[[25, 523], [300, 560], [500, 595], [700, 630], [900, 670], [1665, 760]]),
    "Inconel 718 (Ni)": dict(
        kt=[[25, 11.4], [200, 14.0], [400, 17.5], [600, 20.8], [800, 24.3], [1000, 28.3], [1260, 31]],
        cpt=[[25, 435], [200, 480], [400, 520], [600, 560], [800, 620], [1000, 650], [1260, 700]]),
    "Inconel 625 (Ni)": dict(
        kt=[[25, 9.8], [200, 12.5], [400, 15.7], [600, 18.9], [800, 22.1], [1000, 25.2], [1290, 29]],
        cpt=[[25, 410], [200, 450], [400, 490], [600, 530], [800, 575], [1000, 620], [1290, 670]]),
    "Inconel 600 (Ni)": dict(
        kt=[[25, 14.9], [200, 17.3], [400, 20.5], [600, 23.7], [800, 26.9], [1000, 30.1], [1354, 34]],
        cpt=[[25, 444], [200, 480], [400, 515], [600, 550], [800, 590], [1000, 630], [1354, 680]]),
    "AISI 1045 (steel)": dict(
        kt=[[25, 49.8], [200, 47], [400, 41], [600, 36], [727, 30], [800, 27], [1430, 30]],
        cpt=[[25, 486], [200, 520], [400, 560], [600, 650], [727, 760], [800, 700], [1430, 650]]),
    "AISI 4340 (steel)": dict(
        kt=[[25, 44.5], [200, 42], [400, 38], [600, 33], [800, 27], [1427, 30]],
        cpt=[[25, 475], [200, 510], [400, 560], [600, 640], [727, 750], [800, 690], [1427, 650]]),
    "AISI 316L (steel)": dict(
        kt=[[25, 16.3], [200, 18.3], [400, 21.0], [600, 23.6], [800, 26.2], [1000, 28.7], [1375, 32]],
        cpt=[[25, 500], [200, 525], [400, 550], [600, 575], [800, 600], [1375, 650]]),
    "AISI 304 (steel)": dict(
        kt=[[25, 16.2], [200, 18.3], [400, 21.0], [600, 23.6], [800, 26.2], [1000, 28.7], [1400, 32]],
        cpt=[[25, 500], [200, 525], [400, 550], [600, 575], [800, 600], [1400, 650]]),
    "A36 (mild steel)": dict(
        kt=[[25, 52], [200, 49], [400, 43], [600, 37], [727, 30], [800, 28], [1425, 30]],
        cpt=[[25, 486], [200, 520], [400, 565], [600, 660], [727, 770], [800, 700], [1425, 650]]),
    "Cu OFHC": dict(
        kt=[[25, 386], [200, 379], [400, 366], [600, 352], [800, 339], [1083, 330]],
        cpt=[[25, 385], [200, 398], [400, 417], [600, 435], [800, 450], [1083, 470]]),
}


def interp_prop(table, const, T):
    """Линейная интерполяция свойства по таблице [[T,val],...]; вне диапазона —
       крайнее значение. Если таблицы нет — возвращает const. T скаляр/массив."""
    if not table:
        return const
    arr = np.asarray(table, dtype=float)
    return np.interp(T, arr[:, 0], arr[:, 1])

def _app_dir():
    """Папка для пользовательских файлов: рядом с .exe (frozen) или со скриптом."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _user_file(name):
    return os.path.join(_app_dir(), name)


def _bundled_file(name):
    """Файл-умолчание, упакованный в .exe (PyInstaller _MEIPASS), иначе — рядом."""
    base = getattr(sys, "_MEIPASS", _app_dir())
    return os.path.join(base, name)


def _load_json_db(name):
    """Читать пользовательскую БД рядом с программой; если нет — упакованную по умолч."""
    for path in (_user_file(name), _bundled_file(name)):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            continue
    return {}


def _save_json_db(name, d):
    try:
        with open(_user_file(name), "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_user_materials():
    return _load_json_db("user_materials.json")


def save_user_materials(d):
    return _save_json_db("user_materials.json", d)


def load_user_mu():
    return _load_json_db("user_mu.json")


def save_user_mu(d):
    return _save_json_db("user_mu.json", d)


def all_mu_tables():
    """Встроенные таблицы μ(T) + пользовательские (правки/новые пары) поверх них."""
    tabs = {name: [list(r) for r in tab] for name, tab in MU_TABLES.items()}
    for name, tab in load_user_mu().items():
        try:
            tabs[name] = [[float(r[0]), float(r[1])] for r in tab]
        except Exception:
            continue
    return tabs


def all_materials():
    """Встроенные пресеты (+ таблицы свойств) + пользовательские."""
    mats = {}
    for name, props in PRESETS.items():
        m = dict(props)
        tb = PROP_TABLES.get(name, {})
        m["kt"] = tb.get("kt"); m["cpt"] = tb.get("cpt")
        mats[name] = m
    for name, props in load_user_materials().items():
        m = dict(props)
        m.setdefault("C_emp", None)
        m.setdefault("poly", None)
        m.setdefault("kt", None)
        m.setdefault("cpt", None)
        mats[name] = m
    return mats

# ----------------------------------------------------------------------------
#  Переводы (uk / ru / en)
# ----------------------------------------------------------------------------
TR = {
    "title": dict(uk="AFSD Predictor — пікова T та карти режимів",
                  ru="AFSD Predictor — пиковая T и карты режимов",
                  en="AFSD Predictor — peak temperature & processing maps",
                  zh="AFSD Predictor — 峰值温度与工艺图"),
    "menu_file": dict(uk="Файл", ru="Файл", en="File"),
    "menu_new": dict(uk="Новий проєкт", ru="Новый проект", en="New project"),
    "menu_open": dict(uk="Відкрити проєкт…", ru="Открыть проект…", en="Open project…"),
    "ask_save_title": dict(uk="Незбережені зміни", ru="Несохранённые изменения",
                           en="Unsaved changes"),
    "ask_save_msg": dict(uk="Зберегти зміни в поточному проєкті?",
                         ru="Сохранить изменения в текущем проекте?",
                         en="Save changes to the current project?"),
    "menu_save": dict(uk="Зберегти проєкт", ru="Сохранить проект", en="Save project"),
    "menu_save_as": dict(uk="Зберегти як…", ru="Сохранить как…", en="Save as…"),
    "menu_exit": dict(uk="Вихід", ru="Выход", en="Exit"),
    "menu_export": dict(uk="Знімок", ru="Снимок", en="Snapshot"),
    "menu_png": dict(uk="Зберегти графік PNG…", ru="Сохранить график PNG…",
                     en="Save figure PNG…"),
    "menu_pdf": dict(uk="Зберегти графік PDF (вектор)…", ru="Сохранить график PDF (вектор)…",
                     en="Save figure PDF (vector)…"),
    "menu_svg": dict(uk="Зберегти графік SVG (вектор)…", ru="Сохранить график SVG (вектор)…",
                     en="Save figure SVG (vector)…"),
    "menu_csv": dict(uk="Експорт сітки CSV…", ru="Экспорт сетки CSV…", en="Export grid CSV…"),
    "menu_settings": dict(uk="Налаштування", ru="Настройки", en="Settings"),
    "menu_settings_dlg": dict(uk="Налаштування…", ru="Настройки…", en="Settings…"),
    "menu_language": dict(uk="Мова", ru="Язык", en="Language"),
    "menu_help": dict(uk="Довідка", ru="Справка", en="Help"),
    "menu_about": dict(uk="Про програму", ru="О программе", en="About"),
    "menu_guide": dict(uk="Посібник користувача", ru="Руководство пользователя",
                       en="User guide", zh="用户指南"),
    "btn_guide": dict(uk="Посібник…", ru="Руководство…", en="User guide…", zh="用户指南…"),
    "grp_alloy": dict(uk="Сплав", ru="Сплав", en="Alloy"),
    "grp_props": dict(uk="Властивості сплаву", ru="Свойства сплава", en="Alloy properties"),
    "grp_model": dict(uk="Модель розрахунку", ru="Модель расчёта", en="Calculation model"),
    "grp_ranges": dict(uk="Діапазони параметрів", ru="Диапазоны параметров", en="Parameter ranges"),
    "grp_view": dict(uk="Вигляд і зріз", ru="Вид и срез", en="View & slice"),
    "grp_point": dict(uk="Розрахунок у точці", ru="Расчёт в точке", en="Point evaluation"),
    "lbl_sigma": dict(uk="σ_ref, опорний σ_y [МПа]", ru="σ_ref, опорный σ_y [МПа]",
                      en="σ_ref, reference σ_y [MPa]"),
    "lbl_tref": dict(uk="T_ref (закон розм'якш.) [°C]", ru="T_ref (закон размягч.) [°C]",
                     en="T_ref (softening law) [°C]"),
    "lbl_m": dict(uk="m, показник розм'якшення", ru="m, показатель размягчения",
                  en="m, softening exponent"),
    "lbl_tsol": dict(uk="T_solidus [°C]", ru="T_solidus [°C]", en="T_solidus [°C]"),
    "lbl_t0": dict(uk="T₀, початкова [°C]", ru="T₀, начальная [°C]", en="T₀, initial [°C]"),
    "lbl_c": dict(uk="C, емпір. коеф. ×10⁻⁴ (опц.)", ru="C, эмпир. коэф. ×10⁻⁴ (опц.)",
                  en="C, empirical coef. ×10⁻⁴ (opt.)"),
    "lbl_eta": dict(uk="η, коеф. утримання тепла (0–1)", ru="η, коэф. удержания тепла (0–1)",
                    en="η, heat-retention factor (0–1)"),
    "lbl_rodl": dict(uk="L, виліт прутка [мм] (0 = не враховувати)",
                     ru="L, вылет прутка [мм] (0 = не учитывать)",
                     en="L, unsupported rod length [mm] (0 = off)"),
    "lbl_force": dict(uk="F, осьова сила [кН]", ru="F, осевая сила [кН]", en="F, axial force [kN]"),
    "lbl_mu": dict(uk="μ, коеф. тертя пари", ru="μ, коэф. трения пары",
                   en="μ, friction coeff (pair)"),
    "chk_mutdep": dict(uk="μ(T) таблиця пари:", ru="μ(T) таблица пары:",
                       en="μ(T) pair table:"),
    "rb_muconst": dict(uk="μ = константа", ru="μ = константа", en="μ = constant"),
    "rb_mutab": dict(uk="μ(T) таблиця", ru="μ(T) таблица", en="μ(T) table"),
    "lbl_mupair": dict(uk="Пара:", ru="Пара:", en="Pair:"),
    "rb_subsame": dict(uk="= матеріал прутка", ru="= материал прутка", en="= rod material"),
    "rb_subown": dict(uk="власна підкладка", ru="своя подложка", en="own substrate"),
    "btn_savesub": dict(uk="Зберегти підкладку…", ru="Сохранить подложку…", en="Save substrate…"),
    "btn_mutables": dict(uk="Таблиці μ(T)…", ru="Таблицы μ(T)…", en="μ(T) tables…"),
    "btn_mucalc": dict(uk="μ з моменту…", ru="μ из момента…", en="μ from torque…"),
    "muc_title": dict(uk="μ з моменту і сили", ru="μ из момента и силы", en="μ from torque & force"),
    "muc_M": dict(uk="Крутний момент M [Н·м]", ru="Крутящий момент M [Н·м]", en="Torque M [N·m]"),
    "muc_F": dict(uk="Сила притиску F [кН]", ru="Сила прижима F [кН]", en="Clamp force F [kN]"),
    "muc_Rc": dict(uk="Контактний радіус R_c [мм]", ru="Контактный радиус R_c [мм]",
                   en="Contact radius R_c [mm]"),
    "muc_use": dict(uk="Підставити μ", ru="Подставить μ", en="Use μ"),
    "chk_feedsink": dict(uk="Адвективний сток подачі ρcₚ·V̇",
                         ru="Адвективный сток подачи ρcₚ·V̇",
                         en="Feed advection sink ρcₚ·V̇"),
    "mu_title": dict(uk="Редактор таблиць μ(T)", ru="Редактор таблиц μ(T)", en="μ(T) tables editor"),
    "mu_pairs": dict(uk="Пари матеріалів:", ru="Пары материалов:", en="Material pairs:"),
    "mu_hint": dict(uk="Таблиця «T[°C]  μ» (по рядку); сортується автоматично:",
                    ru="Таблица «T[°C]  μ» (по строке); сортируется автоматически:",
                    en="Table “T[°C]  μ” (one per line); auto-sorted:"),
    "mu_new": dict(uk="Нова пара…", ru="Новая пара…", en="New pair…"),
    "mu_askname": dict(uk="Назва пари (напр. Al–steel):", ru="Название пары (напр. Al–steel):",
                       en="Pair name (e.g. Al–steel):"),
    "mu_empty": dict(uk="Таблиця порожня або некоректна.", ru="Таблица пуста или некорректна.",
                     en="Table is empty or invalid."),
    "mu_del_builtin": dict(uk="Вбудовану пару видалити не можна (лише свої).",
                           ru="Встроенную пару удалить нельзя (только свои).",
                           en="Built-in pair cannot be deleted (only your own)."),
    "lbl_varied": dict(uk="Варіюємо:", ru="Варьируем:", en="Varied:"),
    "rb_range": dict(uk="діапазон", ru="диапазон", en="range"),
    "rb_single": dict(uk="число", ru="число", en="single"),
    "rng_min": dict(uk="min", ru="min", en="min"),
    "rng_max": dict(uk="max", ru="max", en="max"),
    "rng_val": dict(uk="значення", ru="значение", en="value"),
    "need2range": dict(uk="Потрібно ≥2 параметри в режимі «діапазон» для карти",
                       ru="Нужно ≥2 параметра в режиме «диапазон» для карты",
                       en="Need ≥2 parameters set to “range” to build a map"),
    "matrix_n": dict(uk="План: 3^N = %d дослідів", ru="План: 3^N = %d опытов",
                     en="Design: 3^N = %d runs"),
    "rb_feed": dict(uk="подача v_f", ru="подача v_f", en="feed v_f"),
    "rb_force": dict(uk="сила F", ru="сила F", en="force F"),
    "lbl_fmin": dict(uk="F min, сила [кН]", ru="F min, сила [кН]", en="F min, force [kN]"),
    "lbl_fmax": dict(uk="F max, сила [кН]", ru="F max, сила [кН]", en="F max, force [kN]"),
    "lbl_vffix": dict(uk="v_f (фікс.) [мм/с]", ru="v_f (фикс.) [мм/с]", en="v_f (fixed) [mm/s]"),
    "lbl_ffix": dict(uk="F (фікс.) [кН]", ru="F (фикс.) [кН]", en="F (fixed) [kN]"),
    "ax_F": dict(uk="F, осьова сила", ru="F, осевая сила", en="F, axial force"),
    "unit_kN": dict(uk="кН", ru="кН", en="kN"),
    "reg_slide": dict(uk="ковзання", ru="скольжение", en="sliding"),
    "reg_stick": dict(uk="залипання", ru="залипание", en="sticking"),
    "flag_solidus": dict(uk="контакт біля солідусу — верхня межа моделі (потрібен η<1)",
                         ru="контакт у солидуса — верхняя граница модели (нужен η<1)",
                         en="contact at solidus — model upper bound (η<1 needed)"),
    "lbl_rho": dict(uk="ρ прутка [кг/м³]", ru="ρ прутка [кг/м³]", en="ρ rod [kg/m³]"),
    "lbl_cp": dict(uk="cₚ прутка [Дж/кг·К]", ru="cₚ прутка [Дж/кг·К]", en="cₚ rod [J/kg·K]"),
    "lbl_k": dict(uk="k прутка [Вт/м·К]", ru="k прутка [Вт/м·К]", en="k rod [W/m·K]"),
    "grp_pe": dict(uk="Швидкість / конвекція (Pe)", ru="Скорость / конвекция (Pe)",
                   en="Speed / convection (Pe)"),
    "chk_pe": dict(uk="Враховувати швидкість осадження (Pe)",
                   ru="Учитывать скорость осаждения (Pe)",
                   en="Account for deposition speed (Pe)"),
    "lbl_v": dict(uk="v, швидкість траверсу (поступ.) [мм/с]",
                  ru="v, скорость траверса (поступат.) [мм/с]",
                  en="v, traverse (travel) speed [mm/s]"),
    "grp_inmode": dict(uk="Тип вхідних даних", ru="Тип входных данных", en="Input type"),
    "mode_H": dict(uk="Глибина H (класич.)", ru="Глубина H (классич.)", en="Depth H (classic)"),
    "mode_kin": dict(uk="Shoulderless AFSD (пруток)", ru="Shoulderless AFSD (пруток)",
                     en="Shoulderless AFSD (rod)"),
    "mode_shoulder": dict(uk="Shouldered AFSD (MELD)", ru="Shouldered AFSD (MELD)",
                          en="Shouldered AFSD (MELD)"),
    "tab_proc": dict(uk="Схема процесу 3D", ru="Схема процесса 3D", en="Process schematic 3D"),
    "grp_geom": dict(uk="Геометрія (схема)", ru="Геометрия (схема)", en="Geometry (schematic)"),
    "lbl_subL": dict(uk="Довжина підкладки [мм]", ru="Длина подложки [мм]", en="Substrate length [mm]"),
    "lbl_subW": dict(uk="Ширина підкладки [мм]", ru="Ширина подложки [мм]", en="Substrate width [mm]"),
    "lbl_subt": dict(uk="Товщина підкладки [мм]", ru="Толщина подложки [мм]", en="Substrate thick. [mm]"),
    "lbl_traillen": dict(uk="Довжина сліду [мм]", ru="Длина следа [мм]", en="Trail length [mm]"),
    "lbl_rodlen": dict(uk="Виліт прутка (показ) [мм]", ru="Вылет прутка (показ) [мм]",
                       en="Rod length (shown) [mm]"),
    "lbl_shoeth": dict(uk="Товщина шайби [мм]", ru="Толщина шайбы [мм]", en="Shoulder thick. [mm]"),
    "lbl_barlen": dict(uk="Виліт бруска (показ) [мм]", ru="Вылет бруска (показ) [мм]",
                       en="Bar length (shown) [mm]"),
    "geom_note": dict(uk="R_eff та H зони обчислюються з подачі/траверсу автоматично.",
                      ru="R_eff и H зоны вычисляются из подачи/траверса автоматически.",
                      en="R_eff and zone H are computed from feed/traverse automatically."),
    "btn_save_proc": dict(uk="Зберегти схему (PNG)", ru="Сохранить схему (PNG)",
                          en="Save schematic (PNG)"),
    "lbl_txtsize": dict(uk="Розмір тексту", ru="Размер текста", en="Text size"),
    "lbl_style": dict(uk="Оформлення графіка", ru="Оформление графика", en="Plot style"),
    "lbl_lblpad": dict(uk="Відступ назв осей", ru="Отступ названий осей", en="Axis-label pad"),
    "lbl_tickpad": dict(uk="Відступ цифр", ru="Отступ цифр", en="Tick pad"),
    "lbl_ncolors": dict(uk="К-сть кольорів", ru="Кол-во цветов", en="Colors"),
    "lbl_aspect": dict(uk="Співвідношення Ш:В", ru="Соотношение Ш:В", en="Aspect W:H"),
    "lbl_boxpos": dict(uk="Позиція рамки X / Y", ru="Позиция рамки X / Y", en="Box pos X / Y"),
    "lbl_radius": dict(uk="Радіус замість діаметра", ru="Радиус вместо диаметра",
                       en="Radius instead of diameter"),
    "lbl_cbpad": dict(uk="Назва шкали X", ru="Надпись шкалы X", en="Bar-label X"),
    "lbl_cbflip": dict(uk="Назва шкали 180°", ru="Надпись шкалы 180°", en="Bar label 180°"),
    "lbl_boxscale": dict(uk="Масштаб рамки", ru="Масштаб рамки", en="Box scale"),
    "lbl_cbarpos": dict(uk="Положення шкали", ru="Положение шкалы", en="Bar position"),
    "lbl_winfill": dict(uk="Зелена підсвітка вікна", ru="Зелёная подсветка окна",
                        en="Green window fill"),
    "lbl_showreg": dict(uk="Регресія T(x,y) на карті", ru="Регрессия T(x,y) на карте",
                        en="Regression T(x,y) on map"),
    "btn_copyreg": dict(uk="Копіювати LaTeX (T(x,y))", ru="Копировать LaTeX (T(x,y))",
                        en="Copy LaTeX (T(x,y))"),
    "btn_copyreg_full": dict(uk="Копіювати регресію в LaTeX", ru="Копировать регрессию в LaTeX",
                             en="Copy regression as LaTeX"),
    "copied_latex": dict(uk="Рівняння скопійовано в буфер (LaTeX).",
                         ru="Уравнение скопировано в буфер (LaTeX).",
                         en="Equation copied to clipboard (LaTeX)."),
    "lbl_wlo": dict(uk="Нижня межа ×Ts", ru="Нижняя граница ×Ts", en="Lower ×Ts"),
    "lbl_whi": dict(uk="Верхня межа ×Ts", ru="Верхняя граница ×Ts", en="Upper ×Ts"),
    "lbl_abar": dict(uk="a, сторона бруска [мм]", ru="a, сторона бруска [мм]",
                     en="a, bar side [mm]"),
    "lbl_amin": dict(uk="a min, сторона [мм]", ru="a min, сторона [мм]", en="a min, side [mm]"),
    "lbl_amax": dict(uk="a max, сторона [мм]", ru="a max, сторона [мм]", en="a max, side [mm]"),
    "ax_a": dict(uk="a, сторона бруска", ru="a, сторона бруска", en="a, bar side"),
    "lbl_rshoe": dict(uk="R шайби (макс. пляма) [мм]", ru="R шайбы (макс. пятно) [мм]",
                      en="R shoulder (max spot) [mm]"),
    "grp_shoe": dict(uk="Шайба (плече, відвід тепла вгору)",
                     ru="Шайба (плечо, отвод тепла вверх)",
                     en="Shoulder (heat sink upward)"),
    "shoe_none": dict(uk="(без відводу вгору)", ru="(без отвода вверх)",
                      en="(no upward sink)"),
    "lbl_kshoe": dict(uk="k шайби [Вт/м·К]", ru="k шайбы [Вт/м·К]", en="k shoulder [W/m·K]"),
    "shoulder_note": dict(
        uk="R_eff = a²·v↓/(2·H·v→), обмежено R шайби;  тепло вниз (плита) + вгору (шайба).",
        ru="R_eff = a²·v↓/(2·H·v→), ограничено R шайбы;  тепло вниз (плита) + вверх (шайба).",
        en="R_eff = a²·v↓/(2·H·v→), capped by R shoulder;  heat down (plate) + up (shoulder)."),
    "chk_bore": dict(uk="Кільцевий контакт плеча (мінус переріз бруска)",
                     ru="Кольцевой контакт плеча (минус сечение бруска)",
                     en="Annular shoulder contact (minus bar cross-section)"),
    "lbl_D": dict(uk="D, діаметр прутка [мм]", ru="D, диаметр прутка [мм]",
                  en="D, rod diameter [mm]"),
    "lbl_wbead": dict(uk="w, ширина валика [мм]", ru="w, ширина валика [мм]",
                      en="w, bead width [mm]"),
    "chk_beadw": dict(uk="врахувати w:", ru="учесть w:", en="use w:"),
    "btn_clear_pts": dict(uk="Очистити точки", ru="Очистить точки", en="Clear points"),
    "pt_edit_title": dict(uk="Мітка точки", ru="Метка точки", en="Point label"),
    "pt_edit_msg": dict(uk="Нова літера/мітка точки:", ru="Новая буква/метка точки:",
                        en="New point letter/label:"),
    "lbl_vzmin": dict(uk="v_f min, подача [мм/с]", ru="v_f min, подача [мм/с]",
                      en="v_f min, feed [mm/s]"),
    "lbl_vzmax": dict(uk="v_f max, подача [мм/с]", ru="v_f max, подача [мм/с]",
                      en="v_f max, feed [mm/s]"),
    "lbl_vxmin": dict(uk="v_t min, траверс [мм/с]", ru="v_t min, траверс [мм/с]",
                      en="v_t min, traverse [mm/s]"),
    "lbl_vxmax": dict(uk="v_t max, траверс [мм/с]", ru="v_t max, траверс [мм/с]",
                      en="v_t max, traverse [mm/s]"),
    "ax_vz": dict(uk="Вертик. подача v↓, мм/с", ru="Вертик. подача v↓, мм/с",
                  en="Vertical feed v↓, mm/s"),
    "ax_vx": dict(uk="Траверс v→, мм/с", ru="Траверс v→, мм/с", en="Traverse v→, mm/s"),
    "ax_D": dict(uk="Діаметр прутка D, мм", ru="Диаметр прутка D, мм", en="Rod diameter D, mm"),
    "lbl_dmin": dict(uk="D min, діаметр [мм]", ru="D min, диаметр [мм]", en="D min, diameter [mm]"),
    "lbl_dmax": dict(uk="D max, діаметр [мм]", ru="D max, диаметр [мм]", en="D max, diameter [mm]"),
    "axis_x": dict(uk="Вісь X:", ru="Ось X:", en="X axis:"),
    "axis_y": dict(uk="Вісь Y:", ru="Ось Y:", en="Y axis:"),
    "fix_lbl": dict(uk="Фікс.", ru="Фикс.", en="Fix"),
    "chk_tdep": dict(uk="T-залежність k, cₚ (таблиці)", ru="T-зависимость k, cₚ (таблицы)",
                     en="T-dependence k, cₚ (tables)"),
    "btn_tables": dict(uk="Бібліотека k, cₚ(T)…", ru="Библиотека k, cₚ(T)…", en="Library k, cₚ(T)…"),
    "lib_title": dict(uk="Бібліотека температурозалежних властивостей",
                      ru="Библиотека температурозависимых свойств",
                      en="Temperature-dependent property library"),
    "lib_materials": dict(uk="Матеріали", ru="Материалы", en="Materials"),
    "lib_new": dict(uk="Новий…", ru="Новый…", en="New…"),
    "lib_del": dict(uk="Видалити", ru="Удалить", en="Delete"),
    "lib_save": dict(uk="Зберегти", ru="Сохранить", en="Save"),
    "lib_apply": dict(uk="Обрати для прутка", ru="Выбрать для прутка", en="Use for rod"),
    "lib_kT": dict(uk="k(T):  рядки «T  k»  [°C  Вт/м·К]", ru="k(T):  строки «T  k»  [°C  Вт/м·К]",
                   en="k(T):  rows «T  k»  [°C  W/m·K]"),
    "lib_cpT": dict(uk="cₚ(T):  рядки «T  cₚ»  [°C  Дж/кг·К]", ru="cₚ(T):  строки «T  cₚ»  [°C  Дж/кг·К]",
                    en="cₚ(T):  rows «T  cₚ»  [°C  J/kg·K]"),
    "lib_del_builtin": dict(uk="Вбудований матеріал видалити не можна (тільки свої).",
                            ru="Встроенный материал удалить нельзя (только свои).",
                            en="Built-in materials cannot be deleted (only your own)."),
    "unit_mms": dict(uk="мм/с", ru="мм/с", en="mm/s"),
    "kin_note": dict(uk="H виводиться: H = πR²(v↓/v→)/w;  сток подачі у знаменнику.",
                     ru="H выводится: H = πR²(v↓/v→)/w;  сток подачи в знаменателе.",
                     en="H is derived: H = πR²(v↓/v→)/w;  feed sink in the denominator."),
    "grp_props_dep": dict(uk="Властивості прутка (присадки)", ru="Свойства прутка (присадки)",
                          en="Rod (feedstock) properties"),
    "grp_sub": dict(uk="Підкладка", ru="Подложка", en="Substrate"),
    "sub_same": dict(uk="(= матеріал прутка)", ru="(= материал прутка)", en="(= deposit material)"),
    "lbl_subsel": dict(uk="Матеріал підкладки", ru="Материал подложки", en="Substrate material"),
    "lbl_ksub": dict(uk="k підкл. [Вт/м·К]", ru="k подл. [Вт/м·К]", en="k substr. [W/m·K]"),
    "lbl_rhosub": dict(uk="ρ підкл. [кг/м³]", ru="ρ подл. [кг/м³]", en="ρ substr. [kg/m³]"),
    "lbl_cpsub": dict(uk="cₚ підкл. [Дж/кг·К]", ru="cₚ подл. [Дж/кг·К]", en="cₚ substr. [J/kg·K]"),
    "btn_addmat": dict(uk="＋ Додати матеріал…", ru="＋ Добавить материал…", en="＋ Add material…"),
    "ask_matname": dict(uk="Назва матеріалу:", ru="Название материала:", en="Material name:"),
    "mat_added": dict(uk="Матеріал збережено у базу.", ru="Материал сохранён в базу.",
                      en="Material saved to the database."),
    "model_phys": dict(uk="Фізична (ур. 4+10, за k)", ru="Физическая (ур. 4+10, по k)",
                       en="Physical (Eq. 4+10, via k)"),
    "model_emp": dict(uk="Емпіричний коеф. C (ур. 15/16)", ru="Эмпирический коэф. C (ур. 15/16)",
                      en="Empirical coef. C (Eq. 15/16)"),
    "model_poly": dict(uk="Поліноміальна (ур. 17/18)", ru="Полиномиальная (ур. 17/18)",
                       en="Polynomial (Eq. 17/18)"),
    "lbl_wmin": dict(uk="ω min [об/хв]", ru="ω min [об/мин]", en="ω min [rpm]"),
    "lbl_wmax": dict(uk="ω max [об/хв]", ru="ω max [об/мин]", en="ω max [rpm]"),
    "lbl_rmin": dict(uk="R min [мм]  (D = 2R)", ru="R min [мм]  (D = 2R)", en="R min [mm]  (D = 2R)"),
    "lbl_rmax": dict(uk="R max [мм]", ru="R max [мм]", en="R max [mm]"),
    "lbl_hmin": dict(uk="H min [мм]", ru="H min [мм]", en="H min [mm]"),
    "lbl_hmax": dict(uk="H max [мм]", ru="H max [мм]", en="H max [mm]"),
    "rb_2d": dict(uk="2D контур", ru="2D контур", en="2D contour"),
    "rb_3d": dict(uk="3D поверхня", ru="3D поверхность", en="3D surface"),
    "lbl_freeze": dict(uk="Зафіксувати:", ru="Зафиксировать:", en="Fix:"),
    "lbl_slice": dict(uk="Значення зрізу:", ru="Значение среза:", en="Slice value:"),
    "chk_swap": dict(uk="Поміняти осі X ↔ Y", ru="Поменять оси X ↔ Y", en="Swap axes X ↔ Y"),
    "lbl_color": dict(uk="Колір:", ru="Цвет:", en="Colour:"),
    "color_full": dict(uk="весь діапазон", ru="весь диапазон", en="full range"),
    "color_win": dict(uk="лише робоче вікно", ru="только рабочее окно", en="window only"),
    "btn_build": dict(uk="▶ Побудувати", ru="▶ Построить", en="▶ Plot"),
    "btn_calc": dict(uk="Розрахувати T_peak", ru="Рассчитать T_peak", en="Compute T_peak"),
    "reg_eq_title": dict(uk="Регресійне рівняння T_peak", ru="Регрессионное уравнение T_peak",
                         en="Regression equation T_peak"),
    # подписи под иконками тулбара
    "cap_reset": dict(uk="Скид", ru="Сброс", en="Reset", zh="复位"),
    "cap_back": dict(uk="Назад", ru="Назад", en="Back", zh="后退"),
    "cap_fwd": dict(uk="Вперед", ru="Вперёд", en="Fwd", zh="前进"),
    "cap_pan": dict(uk="Рух", ru="Сдвиг", en="Pan", zh="平移"),
    "cap_zoom": dict(uk="Зум", ru="Зум", en="Zoom", zh="缩放"),
    "cap_margins": dict(uk="Поля", ru="Поля", en="Margins", zh="边距"),
    "cap_clear": dict(uk="Очист.", ru="Очист.", en="Clear", zh="清除"),
    # группы панели оформления
    "sty_text": dict(uk="Текст і підписи", ru="Текст и подписи", en="Text & labels", zh="文字与标签"),
    "sty_window": dict(uk="Вікно стабільності", ru="Окно стабильности", en="Stability window",
                       zh="稳定窗口"),
    "sty_box": dict(uk="Рамка параметрів", ru="Рамка параметров", en="Parameter box", zh="参数框"),
    "sty_bar": dict(uk="Кольорова шкала", ru="Цветовая шкала", en="Colorbar", zh="色条"),
    "sty_2d": dict(uk="Тільки 2D", ru="Только 2D", en="2D only", zh="仅 2D"),
    "sty_3d": dict(uk="Тільки 3D", ru="Только 3D", en="3D only", zh="仅 3D"),
    "sty_reg": dict(uk="Регресія на карті", ru="Регрессия на карте", en="Regression on map",
                    zh="图上回归"),
    "lbl_boxx": dict(uk="Поз. X", ru="Поз. X", en="Pos X", zh="位置 X"),
    "lbl_boxy": dict(uk="Поз. Y", ru="Поз. Y", en="Pos Y", zh="位置 Y"),
    "lbl_elev": dict(uk="Підйом°", ru="Подъём°", en="Elevation°", zh="仰角°"),
    "lbl_azim": dict(uk="Азимут°", ru="Азимут°", en="Azimuth°", zh="方位°"),
    "lbl_mesh": dict(uk="Сітка 3D", ru="Сетка 3D", en="3D mesh", zh="网格"),
    "tip_home": dict(uk="Скинути вид", ru="Сбросить вид", en="Reset view"),
    "tip_back": dict(uk="Назад", ru="Назад", en="Back"),
    "tip_forward": dict(uk="Вперед", ru="Вперёд", en="Forward"),
    "tip_pan": dict(uk="Панорама (перетягування)", ru="Панорама (перетаскивание)", en="Pan"),
    "tip_zoom": dict(uk="Збільшення рамкою", ru="Увеличение рамкой", en="Zoom to rectangle"),
    "tip_config": dict(uk="Поля/відступи", ru="Поля/отступы", en="Subplot margins"),
    "tip_clearpts": dict(uk="Очистити точки", ru="Очистить точки", en="Clear points"),
    "btn_png": dict(uk="Зберегти рисунок (PNG)", ru="Сохранить рисунок (PNG)", en="Save figure (PNG)"),
    "btn_csv": dict(uk="Експорт сітки (CSV)", ru="Экспорт сетки (CSV)", en="Export grid (CSV)"),
    "tab_plot": dict(uk="Карта / Поверхня", ru="Карта / Поверхность", en="Map / Surface"),
    "tab_formulas": dict(uk="Формули", ru="Формулы", en="Formulas"),
    "tab_matrix": dict(uk="Матриця планування", ru="Матрица планирования", en="Design matrix"),
    "unit_mpa": dict(uk="МПа", ru="МПа", en="MPa"),
    "mat_refresh": dict(uk="Оновити матрицю", ru="Обновить матрицу", en="Refresh matrix"),
    "mat_export": dict(uk="Експорт матриці (CSV)", ru="Экспорт матрицы (CSV)", en="Export matrix (CSV)"),
    "emp_from_k": dict(uk="C = (2/3)π/(4k) — виведено з k",
                       ru="C = (2/3)π/(4k) — выведено из k",
                       en="C = (2/3)π/(4k) — derived from k"),
    "reg_paper": dict(uk="(коефіцієнти зі статті)", ru="(коэффициенты из статьи)",
                      en="(coefficients from the paper)"),
    "reg_fitted": dict(uk="(підігнано по точках плану 3ᴺ; модель: фізична)",
                       ru="(построено по точкам плана 3ᴺ; модель: физическая)",
                       en="(fitted from the 3ᴺ design points; physical model)"),
    "mat_note": dict(
        uk="Повний план 3ᴺ (N факторів). Рівні −1/0/+1 = min / середина / max.\n"
           "τ та T_peak — самоузгоджені (ітераційний підбір), τ = σ_y(T_peak)/√3.",
        ru="Полный план 3ᴺ (N факторов). Уровни −1/0/+1 = min / середина / max.\n"
           "τ и T_peak — самосогласованные (итерационный подбор), τ = σ_y(T_peak)/√3.",
        en="Full 3ᴺ design (N factors). Levels −1/0/+1 = min / mid / max.\n"
           "τ and T_peak are self-consistent (iterative), τ = σ_y(T_peak)/√3."),
    "ax_w": dict(uk="Кутова швидкість ω, об/хв", ru="Угловая скорость ω, об/мин",
                 en="Angular velocity ω, rpm"),
    "ax_r": dict(uk="Радіус стрижня R, мм", ru="Радиус стержня R, мм", en="Tool radius R, mm"),
    "ax_h": dict(uk="Глибина контакту H, мм", ru="Глубина контакта H, мм", en="Contact depth H, mm"),
    "unit_rpm": dict(uk="об/хв", ru="об/мин", en="rpm"),
    "unit_mm": dict(uk="мм", ru="мм", en="mm"),
    "st_in": dict(uk="В ВІКНІ ✓", ru="В ОКНЕ ✓", en="IN WINDOW ✓"),
    "st_below": dict(uk="НИЖЧЕ вікна", ru="НИЖЕ окна", en="BELOW window"),
    "st_above": dict(uk="ВИЩЕ вікна", ru="ВЫШЕ окна", en="ABOVE window"),
    "res_window": dict(uk="вікно", ru="окно", en="window"),
    "ttl_slice": dict(uk="зріз", ru="срез", en="slice"),
    "ttl_window": dict(uk="вікно", ru="окно", en="window"),
    "ttl_model": dict(uk="модель", ru="модель", en="model"),
    "err_num": dict(uk="Перевірте числові поля.", ru="Проверьте числовые поля.",
                    en="Check the numeric fields."),
    "err_minmax": dict(uk="max має бути більше за min.", ru="max должен быть больше min.",
                       en="max must be greater than min."),
    "err": dict(uk="Помилка", ru="Ошибка", en="Error"),
    "saved": dict(uk="Збережено", ru="Сохранено", en="Saved"),
    "no_data": dict(uk="Немає даних", ru="Нет данных", en="No data"),
    "no_data_msg": dict(uk="Спочатку побудуйте графік.", ru="Сначала постройте график.",
                        en="Build a plot first."),
    "set_title": dict(uk="Налаштування", ru="Настройки", en="Settings"),
    "set_lang": dict(uk="Мова програми", ru="Язык программы", en="Application language"),
    "set_uifont": dict(uk="Шрифт програми", ru="Шрифт программы", en="Application font"),
    "set_uisize": dict(uk="Розмір шрифту програми", ru="Размер шрифта программы",
                       en="Application font size"),
    "set_gfont": dict(uk="Шрифт графіка", ru="Шрифт графика", en="Graph font"),
    "set_gsize": dict(uk="Розмір шрифту графіка", ru="Размер шрифта графика",
                      en="Graph font size"),
    "set_cbarpad": dict(uk="Відступ шкали від графіка", ru="Отступ шкалы от графика",
                        en="Colorbar gap from plot"),
    "set_n3d": dict(uk="Щільність 3D-сітки (дрібніше)", ru="Плотность 3D-сетки (мельче)",
                    en="3D mesh density (finer)"),
    "set_ok": dict(uk="OK", ru="OK", en="OK"),
    "set_cancel": dict(uk="Скасувати", ru="Отмена", en="Cancel"),
    "set_apply": dict(uk="Застосувати", ru="Применить", en="Apply"),
    "db_note": dict(
        uk="Примітка: параметри сплавів (крім AA6061/AZ31B) — номінальні\n"
           "літературні значення типу Джонсона–Кука; перевіряйте перед\n"
           "відповідальними розрахунками.",
        ru="Примечание: параметры сплавов (кроме AA6061/AZ31B) — номинальные\n"
           "литературные значения типа Джонсона–Кука; проверяйте перед\n"
           "ответственными расчётами.",
        en="Note: alloy parameters (except AA6061/AZ31B) are nominal\n"
           "Johnson–Cook literature values; verify before critical use."),

    # --- строки Qt-интерфейса ---
    "menu_saveas": dict(uk="Зберегти як…", ru="Сохранить как…", en="Save as…"),
    "menu_lang": dict(uk="Мова", ru="Язык", en="Language"),
    "menu_theme": dict(uk="Темна тема", ru="Тёмная тема", en="Dark theme"),
    "menu_materials": dict(uk="Матеріали", ru="Материалы", en="Materials"),
    "menu_lib": dict(uk="База матеріалів…", ru="База материалов…", en="Material database…"),
    "menu_exp_csv": dict(uk="Сітку в CSV…", ru="Сетку в CSV…", en="Grid to CSV…"),
    "menu_exp_matrix": dict(uk="Матрицю в CSV…", ru="Матрицу в CSV…", en="Design matrix to CSV…"),
    "tab_process": dict(uk="Режим", ru="Режим", en="Process"),
    "tab_material": dict(uk="Матеріал", ru="Материал", en="Material"),
    "tab_style": dict(uk="Оформлення", ru="Оформление", en="Appearance"),
    "tab_map": dict(uk="Карта", ru="Карта", en="Map"),
    "grp_proc": dict(uk="Процес", ru="Процесс", en="Process"),
    "grp_params": dict(uk="Параметри режиму", ru="Параметры режима", en="Process parameters"),
    "grp_axes": dict(uk="Осі карти", ru="Оси карты", en="Map axes"),
    "grp_extra": dict(uk="Додатково", ru="Дополнительно", en="Advanced"),
    "grp_dep": dict(uk="Пруток (присадка)", ru="Пруток (присадка)", en="Rod (feedstock)"),
    "grp_sub": dict(uk="Підкладка", ru="Подложка", en="Substrate"),
    "grp_friction": dict(uk="Контакт", ru="Контакт", en="Contact"),
    "grp_view": dict(uk="Вигляд", ru="Вид", en="View"),
    "grp_window": dict(uk="Технологічне вікно", ru="Технологическое окно", en="Process window"),
    "grp_text": dict(uk="Текст і сітка", ru="Текст и сетка", en="Text and mesh"),
    "grp_3d": dict(uk="Ракурс 3D", ru="Ракурс 3D", en="3D view angle"),
    "btn_point": dict(uk="Розрахувати точку", ru="Рассчитать точку", en="Evaluate point"),
    "btn_clearpts": dict(uk="Очистити точки", ru="Очистить точки", en="Clear points"),
    "hdr_min": dict(uk="мін", ru="мин", en="min"),
    "hdr_max": dict(uk="макс", ru="макс", en="max"),
    "hdr_point": dict(uk="точка", ru="точка", en="point"),
    "lbl_held": dict(uk="Утримуються: ", ru="Удерживаются: ", en="Held: "),
    "lbl_regime": dict(uk="режим", ru="режим", en="regime"),
    "lbl_fs": dict(uk="Розмір тексту", ru="Размер текста", en="Text size"),
    "lbl_levels": dict(uk="Градацій кольору", ru="Градаций цвета", en="Colour levels"),
    "lbl_n3d": dict(uk="Сітка 3D", ru="Сетка 3D", en="3D mesh"),
    "lbl_elev": dict(uk="Підйом", ru="Подъём", en="Elevation"),
    "lbl_azim": dict(uk="Азимут", ru="Азимут", en="Azimuth"),
    "lbl_kshoe": dict(uk="k плеча", ru="k плеча", en="k shoulder"),
    "chk_subsame": dict(uk="= матеріал прутка", ru="= материал прутка", en="= rod material"),
    "chk_mutdep": dict(uk="μ залежить від T (таблиця пари)",
                       ru="μ зависит от T (таблица пары)",
                       en="μ depends on T (pair table)"),
    "chk_pe": dict(uk="Швидкісна поправка G(Pe)", ru="Скоростная поправка G(Pe)",
                   en="Moving-source correction G(Pe)"),
    "chk_bore": dict(uk="Кільцевий контакт плеча", ru="Кольцевой контакт плеча",
                     en="Annular shoulder contact"),
    "chk_winfill": dict(uk="Підсвітити вікно", ru="Подсветить окно", en="Highlight window"),
    "copied": dict(uk="Скопійовано в буфер", ru="Скопировано в буфер", en="Copied to clipboard"),
    "mat_name": dict(uk="Назва", ru="Название", en="Name"),
    "mat_save": dict(uk="Зберегти", ru="Сохранить", en="Save"),
    "mat_del": dict(uk="Видалити", ru="Удалить", en="Delete"),
    "no_data_msg2": dict(uk="Спочатку побудуйте карту", ru="Сначала постройте карту",
                         en="Build the map first"),
}

# Китайский (中文): переведены основные элементы интерфейса; остальное падает на
# английский (см. App.t). Шифры материалов не переводятся (это ключи базы).
ZH = {
    "title": "AFSD Predictor — 峰值温度与工艺图",
    "menu_file": "文件", "menu_open": "打开项目…", "menu_save": "保存项目",
    "menu_save_as": "另存为…", "menu_exit": "退出", "menu_export": "快照",
    # --- строки Qt-интерфейса ---
    "menu_saveas": "另存为…", "menu_lang": "语言", "menu_theme": "深色主题",
    "menu_materials": "材料", "menu_lib": "材料库…",
    "menu_exp_csv": "网格导出 CSV…", "menu_exp_matrix": "设计矩阵导出 CSV…",
    "tab_process": "工艺", "tab_material": "材料", "tab_style": "外观",
    "tab_map": "云图", "grp_proc": "工艺", "grp_params": "工艺参数",
    "grp_axes": "云图坐标轴", "grp_extra": "高级", "grp_dep": "棒材（填充）",
    "grp_sub": "基板", "grp_friction": "接触", "grp_view": "视图",
    "grp_window": "工艺窗口", "grp_text": "文字与网格", "grp_3d": "三维视角",
    "btn_point": "计算该点", "btn_clearpts": "清除标记点",
    "hdr_min": "最小", "hdr_max": "最大", "hdr_point": "点",
    "lbl_held": "固定：", "lbl_regime": "状态", "lbl_fs": "文字大小",
    "lbl_levels": "颜色级数", "lbl_n3d": "三维网格", "lbl_elev": "仰角",
    "lbl_azim": "方位角", "lbl_kshoe": "轴肩 k",
    "chk_subsame": "= 棒材材料", "chk_mutdep": "μ 随温度（配对表）",
    "chk_pe": "移动热源修正 G(Pe)", "chk_bore": "环形轴肩接触",
    "chk_winfill": "高亮工艺窗口", "copied": "已复制到剪贴板",
    "mat_name": "名称", "mat_save": "保存", "mat_del": "删除",
    "no_data_msg2": "请先生成云图",
    "menu_png": "保存图 PNG…", "menu_pdf": "保存图 PDF（矢量）…",
    "menu_svg": "保存图 SVG（矢量）…", "menu_csv": "导出网格 CSV…",
    "menu_settings": "设置", "menu_settings_dlg": "设置…", "menu_language": "语言",
    "menu_help": "帮助", "menu_about": "关于",
    "tab_plot": "工艺图 / 曲面", "tab_matrix": "试验设计矩阵",
    "grp_alloy": "合金", "grp_inmode": "输入类型", "grp_props_dep": "棒材属性",
    "grp_sub": "基板", "grp_ranges": "参数范围", "grp_view": "视图与切片",
    "grp_point": "单点计算", "grp_shoe": "肩套（向上散热）",
    "mode_kin": "无肩 AFSD（棒材）", "mode_shoulder": "有肩 AFSD（MELD）",
    "btn_build": "▶ 绘图", "btn_calc": "计算 T_peak", "btn_addmat": "＋ 添加材料…",
    "btn_clear_pts": "清除点", "btn_png": "保存图 (PNG)", "btn_csv": "导出网格 (CSV)",
    "btn_savesub": "保存基板…", "btn_mutables": "μ(T) 表…", "btn_mucalc": "由扭矩求 μ…",
    "btn_tables": "库 k, cₚ(T)…", "rb_2d": "2D 等值线", "rb_3d": "3D 曲面",
    "axis_x": "X 轴", "axis_y": "Y 轴", "fix_lbl": "固定",
    "rb_range": "范围", "rb_single": "单值", "rng_min": "min", "rng_max": "max",
    "rng_val": "数值", "lbl_varied": "变量：",
    "rb_muconst": "μ = 常数", "rb_mutab": "μ(T) 表", "lbl_mupair": "材料对：",
    "rb_subsame": "= 棒材材料", "rb_subown": "自定义基板",
    "color_full": "全范围", "color_win": "仅工作窗口", "lbl_color": "颜色",
    "lbl_style": "图形外观", "chk_tdep": "k, cₚ 随温度（表）",
    "chk_feedsink": "进给对流散热 ρcₚ·V̇", "lbl_mu": "μ，摩擦系数",
    "lbl_eta": "η，热保留系数 (0–1)", "lbl_force": "F，轴向力 [kN]",
    "lbl_rodl": "L，棒材伸出长度 [mm]（0 = 关闭）",
    "mat_refresh": "刷新", "mat_export": "导出 CSV", "set_ok": "确定", "set_cancel": "取消",
    "saved": "已保存", "err": "错误", "reg_eq_title": "回归方程 T_peak",
    "btn_copyreg_full": "复制回归 LaTeX",
}

APP_NAME = "AFSD Predictor"

ABOUT_TEXT = dict(
    uk=(APP_NAME + " — калькулятор пікової температури та карт режимів\n"
        "процесу Additive Friction Stir Deposition (AFSD).\n\n"
        "Автор: Ярослав Двірник\n"
        "к.т.н., доцент кафедри «Технологія авіаційних двигунів»,\n"
        "Національний університет «Запорізька політехніка».\n\n"
        "E-mail: dvirnyk@gmail.com\n"
        "Тел.: +380 50 584 5697\n"
        "ORCID: 0000-0001-5439-5413"),
    ru=(APP_NAME + " — калькулятор пиковой температуры и карт режимов\n"
        "процесса Additive Friction Stir Deposition (AFSD).\n\n"
        "Автор: Ярослав Двирнык\n"
        "к.т.н., доцент кафедры «Технология авиационных двигателей»,\n"
        "Национальный университет «Запорожская политехника».\n\n"
        "E-mail: dvirnyk@gmail.com\n"
        "Тел.: +380 50 584 5697\n"
        "ORCID: 0000-0001-5439-5413"),
    en=(APP_NAME + " — peak-temperature and processing-map calculator\n"
        "for Additive Friction Stir Deposition (AFSD).\n\n"
        "Author: Yaroslav Dvirnyk\n"
        "PhD (Cand. of Sci.), Associate Professor,\n"
        "Department of Aircraft Engine Technology,\n"
        "Zaporizhzhia Polytechnic National University.\n\n"
        "E-mail: dvirnyk@gmail.com\n"
        "Phone: +380 50 584 5697\n"
        "ORCID: 0000-0001-5439-5413"),
    zh=(APP_NAME + " — 用于搅拌摩擦增材制造 (AFSD) 的\n"
        "峰值温度与工艺图计算器。\n\n"
        "作者：Yaroslav Dvirnyk（亚罗斯拉夫·德维尔尼克）\n"
        "博士，副教授，\n"
        "航空发动机工艺系，扎波罗热国立理工大学。\n\n"
        "E-mail: dvirnyk@gmail.com\n"
        "电话: +380 50 584 5697\n"
        "ORCID: 0000-0001-5439-5413"),
)

# ----------------------------------------------------------------------------
#  Руководство пользователя (открывается из меню «Справка»)
# ----------------------------------------------------------------------------
GUIDE_TEXT = dict(
    en="""AFSD Predictor — USER GUIDE

1. PURPOSE
AFSD Predictor computes the peak contact temperature of Additive Friction Stir
Deposition (AFSD) and builds processing maps (2D contour / 3D surface) over the
chosen parameters, highlighting the stability window 0.6…0.9·T_solidus. The model
is FORCE-CONTROLLED: axial force F and friction coefficient μ are inputs.

2. QUICK START
  1) Pick the feedstock alloy (Alloy).
  2) Choose the process: Shoulderless (round rod) or Shouldered (square bar
     through a shoulder).
  3) Set rod & substrate properties, axial force F, friction μ and efficiency η.
  4) In "Parameter ranges" mark which parameters VARY ("range") and which are
     fixed ("single"). A map needs at least TWO "range" parameters.
  5) Choose the X and Y axes, then press ▶ Plot.
  6) Use "Point evaluation" to compute T at a specific point.
  7) Read the design matrix and the regression equation in the "Design matrix" tab.

3. INPUT TYPE
  • Shoulderless AFSD — round rod. Factors: ω, v_f (feed), v_t (traverse),
    D (rod diameter), F. Bead width = rod diameter (2R).
  • Shouldered AFSD (MELD) — square bar a×a fed through a rotating shoulder at
    gap H; the spot radius follows from mass balance. Factors: ω, v_f, v_t,
    H (gap), a (bar side), F. The shoulder conducts heat upward (its own material).

4. MATERIALS
  • Alloy dropdown: built-in alloys + your saved ones. "+ Add material…" saves the
    current rod properties under a name.
  • Substrate: "= rod material" (copies the rod) or "own substrate" (pick a
    material / edit k, ρ, cₚ; "Save substrate…" stores it in the database).
  • Friction μ of the contact pair: "μ = constant" or "μ(T) table" (choose a pair
    table). "μ(T) tables…" opens an editor (add / edit / delete pair tables).
    "μ from torque…" computes μ = 3·M / (2·F·Rc) from spindle torque and force.
  • k, cₚ(T): tick "T-dependence" to use temperature tables (interpolated
    self-consistently). "Library k, cₚ(T)…" edits the tables per material.

5. PARAMETERS — RANGE vs SINGLE
Each parameter has a toggle: "range" (min/max — enters the design matrix and may be
an axis) or "single" (one fixed value). The plan size is 3^N where N = number of
"range" parameters: fixing 3 of 5 keeps the matrix small (3² = 9 runs). The map
plots two "range" parameters on X/Y; extra "range" ones get a slider; "single"
ones are held constant.
  • η — heat-input efficiency (0–1): the lumped calibration coefficient. η = 1 is
    the adiabatic upper bound; lower η to match a measured temperature.
  • F — axial force [kN];  μ — friction coefficient of the contact pair.

6. THE MAP
  • 2D contour or 3D surface (View & slice, or the ▦ / ◳ toolbar buttons).
  • Colour: "full range" (whole palette) or "window only" (palette inside
    0.6…0.9·T_s, white outside).
  • The boxed annotation lists the fixed parameters; dashed lines are the window
    bounds (0.6·T_s and 0.9·T_s).

7. POINT EVALUATION & POINTS ON THE MAP
  • Enter a point and press "Compute T_peak": you get T (°C and K), window status,
    H / R_eff, Pe, G, contact pressure p, contact shear τc and the regime
    (sliding / sticking) with the crossover T*. A ⚠ flag means the contact sits at
    the solidus (lower η or add a sink).
  • Each computed point is dropped on the map with a letter (A, B, …). Hover a
    point to show a red ✕ (click it to delete); double-click the label to rename.
    "Clear points" removes them all.

8. DESIGN MATRIX & REGRESSION
  • The "Design matrix" tab shows the full 3^N plan: coded factors, real values,
    τ and T_peak (°C / K). "Export matrix (CSV)" saves it.
  • The least-squares regression T_peak(factors) is shown as one line.
    "Copy regression as LaTeX" copies it ready to paste into a paper. You can also
    overlay the reduced T(x,y) on the map (Plot style → "Regression on map") and
    copy that.

9. PLOT STYLE (journal-quality figures)
The scrollable "Plot style" strip under the graph controls text size, label / tick
pads, the parameter box (scale, position), the colorbar (position, label X, 180°),
window limits (×T_s), radius-vs-diameter, colours, aspect ratio, etc. 2D and 3D
keep SEPARATE settings (except the temperature window); 3D adds elevation, azimuth
and mesh density. Save the figure as PNG (raster) or PDF / SVG (vector) from the
toolbar above the graph.

10. PROJECTS, EXPORT & HOTKEYS
  • File: New (Ctrl+N), Open (Ctrl+O), Save (Ctrl+S), Save as (Ctrl+Shift+S).
    Unsaved changes are guarded on New / Open / window close.
  • Snapshot: PNG (Ctrl+Shift+P), PDF (Ctrl+Shift+D), SVG (Ctrl+Shift+G),
    grid CSV (Ctrl+Shift+E).
  • Language: Settings → Language. Material codes are never translated.

11. THE MODEL (brief)
  p = F / (π·Rc²)
  τy(T) = (σ_ref/√3)·[1 − ((T−T0)/(T_sol−T0))^m]
  τc = min(μ·p, τy)                         (contact shear)
  Q  = (2/3)·π·τc·ω·Rc³                     (contact FACE only)
  Sink = 4·k_sub·Rc (+ 4·k_sh·Rc shouldered) + ρ_dep·cₚ·V̇   (feed advection)
  T_peak = T0 + η·G(Pe)·Q / Sink            (solved self-consistently)
Two regimes: sliding (τc = μp, T scales with η) and sticking near the solidus
(τc = τy, where η has little leverage). Conduction into the consumable rod is
deliberately absorbed into η.
""",
    ru="""AFSD Predictor — РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ

1. НАЗНАЧЕНИЕ
AFSD Predictor рассчитывает пиковую температуру контакта процесса Additive Friction
Stir Deposition (AFSD) и строит карты режимов (2D-контур / 3D-поверхность) по
выбранным параметрам, выделяя окно стабильности 0.6…0.9·T_solidus. Модель
ФОРС-КОНТРОЛИРУЕМАЯ: осевая сила F и коэффициент трения μ — входные данные.

2. БЫСТРЫЙ СТАРТ
  1) Выберите сплав прутка (Сплав).
  2) Выберите процесс: Shoulderless (круглый пруток) или Shouldered (квадратный
     брусок через шайбу).
  3) Задайте свойства прутка и подложки, силу F, трение μ и КПД η.
  4) В «Диапазоны параметров» отметьте, какие параметры варьируются («диапазон»),
     а какие фиксированы («число»). Для карты нужно ≥2 параметров в «диапазоне».
  5) Выберите оси X и Y и нажмите ▶ Построить.
  6) «Расчёт в точке» — температура для конкретной точки.
  7) Матрица планирования и регрессионное уравнение — во вкладке «Матрица».

3. ТИП ВХОДНЫХ ДАННЫХ
  • Shoulderless AFSD — круглый пруток. Факторы: ω, v_f (подача), v_t (траверс),
    D (диаметр прутка), F. Ширина валика = диаметр прутка (2R).
  • Shouldered AFSD (MELD) — квадратный брусок a×a подаётся через вращающуюся
    шайбу с зазором H; радиус пятна — из массового баланса. Факторы: ω, v_f, v_t,
    H (зазор), a (сторона бруска), F. Шайба отводит тепло вверх (свой материал).

4. МАТЕРИАЛЫ
  • Список сплавов: встроенные + ваши. «＋ Добавить материал…» сохраняет текущие
    свойства прутка под именем.
  • Подложка: «= материал прутка» (копирует пруток) или «своя подложка» (выбор
    материала / правка k, ρ, cₚ; «Сохранить подложку…» — в базу).
  • Трение μ пары: «μ = константа» или «μ(T) таблица» (выберите таблицу пары).
    «Таблицы μ(T)…» — редактор (добавить / править / удалить). «μ из момента…»
    считает μ = 3·M / (2·F·Rc) по крутящему моменту и силе.
  • k, cₚ(T): галочка «T-зависимость» включает табличные значения (самосогласованная
    интерполяция). «Библиотека k, cₚ(T)…» — правка таблиц по материалам.

5. ПАРАМЕТРЫ — ДИАПАЗОН или ЧИСЛО
У каждого параметра переключатель: «диапазон» (min/max — входит в матрицу и может
быть осью) или «число» (одно фиксированное значение). Размер плана = 3^N, где N —
число «диапазонных» параметров: зафиксировав 3 из 5, получаете маленькую матрицу
(3² = 9 опытов). На карте две «диапазонные» величины идут на X/Y; лишние получают
слайдер; «числовые» держатся постоянными.
  • η — КПД тепловложения (0–1): калибровочный коэффициент. η = 1 — адиабатическая
    верхняя оценка; снижайте η под измеренную температуру.
  • F — осевая сила [кН];  μ — коэффициент трения пары.

6. КАРТА
  • 2D-контур или 3D-поверхность (Вид и срез, либо кнопки ▦ / ◳ на панели).
  • Цвет: «весь диапазон» или «только рабочее окно» (палитра внутри 0.6…0.9·T_s,
    вне — белый фон).
  • Рамка перечисляет фиксированные параметры; пунктир — границы окна.

7. РАСЧЁТ В ТОЧКЕ И ТОЧКИ НА КАРТЕ
  • Введите точку и нажмите «Рассчитать T_peak»: T (°C и K), статус окна, H / R_eff,
    Pe, G, давление p, касательное τc и режим (скольжение / залипание) с переходом
    T*. Значок ⚠ — контакт у солидуса (нужен η < 1 или доп. сток).
  • Каждая рассчитанная точка ставится на карту с буквой (A, B, …). Наведите курсор
    — появится красный ✕ (клик — удалить); двойной клик по метке — переименовать.
    «Очистить точки» — убрать все.

8. МАТРИЦА И РЕГРЕССИЯ
  • Вкладка «Матрица» показывает полный план 3^N: кодированные факторы, реальные
    значения, τ и T_peak (°C / K). «Экспорт матрицы (CSV)» сохраняет.
  • МНК-регрессия T_peak(факторы) — в одну строку. «Копировать регрессию в LaTeX»
    копирует готовое уравнение. На карте можно наложить сокращённое T(x,y)
    (Plot style → «Регрессия на карте») и скопировать его.

9. ОФОРМЛЕНИЕ ГРАФИКА (для статьи)
Прокручиваемая полоса «Plot style» под графиком управляет размером текста,
отступами подписей/цифр, рамкой параметров (масштаб, позиция), цветовой шкалой
(позиция, надпись X, 180°), границами окна (×T_s), радиус/диаметр, числом цветов,
аспектом и т.д. У 2D и 3D — РАЗДЕЛЬНЫЕ настройки (кроме температурного окна); в 3D
добавлены подъём, азимут и плотность сетки. Сохранение: PNG (растр) или PDF / SVG
(вектор) — с панели над графиком.

10. ПРОЕКТЫ, ЭКСПОРТ И ГОРЯЧИЕ КЛАВИШИ
  • Файл: Новый (Ctrl+N), Открыть (Ctrl+O), Сохранить (Ctrl+S),
    Сохранить как (Ctrl+Shift+S). Несохранённые правки запрашиваются при
    создании/открытии/закрытии.
  • Снимок: PNG (Ctrl+Shift+P), PDF (Ctrl+Shift+D), SVG (Ctrl+Shift+G),
    сетка CSV (Ctrl+Shift+E).
  • Язык: Настройки → Язык. Шифры материалов не переводятся.

11. МОДЕЛЬ (кратко)
  p = F / (π·Rc²)
  τy(T) = (σ_ref/√3)·[1 − ((T−T0)/(T_sol−T0))^m]
  τc = min(μ·p, τy)                         (касательное на контакте)
  Q  = (2/3)·π·τc·ω·Rc³                     (только ТОРЕЦ контакта)
  Сток = 4·k_подл·Rc (+ 4·k_шайбы·Rc у shouldered) + ρ_прут·cₚ·V̇   (адвекция подачи)
  T_peak = T0 + η·G(Pe)·Q / Сток            (самосогласованно)
Два режима: скольжение (τc = μp, T линейна по η) и залипание у солидуса
(τc = τy, где η почти не влияет). Кондукция в пруток намеренно поглощена в η.
""",
)
GUIDE_TEXT["uk"] = GUIDE_TEXT["ru"]
GUIDE_TEXT["zh"] = GUIDE_TEXT["en"]


# ----------------------------------------------------------------------------
#  Физическое ядро
# ----------------------------------------------------------------------------
def c_to_k(t_c):
    return t_c + 273.15


def G_pe(Pe):
    """Скоростная поправка движущегося дискового источника (Розенталь),
       ИЗОТЕРМИЧЕСКОЕ распределение потока по диску (Carslaw & Jaeger §10.4):
       q(ρ) = Q / (2πR·sqrt(R²−ρ²)) — согласовано со стационарным пределом
       Q/(4kR) и кондуктансами стоков 4kR. Ревизия по R1-C6 (MTCOMM).
       G(Pe) = (2/π)·∫₀¹ exp(−(Pe/2)s)·I₀((Pe/2)s)/sqrt(1−s²) ds,  G(0)=1.
       Подстановка s=sin(t) устраняет интегрируемую особенность в s=1.
       Pe — скаляр или массив; возвращает ту же форму."""
    Pe = np.asarray(Pe, dtype=float)
    t = np.linspace(0.0, math.pi / 2.0, 256)
    s = np.sin(t)
    arg = (np.clip(Pe, 0.0, 60.0)[..., None] / 2.0) * s
    integ = np.exp(-arg) * np.i0(arg)
    return (2.0 / math.pi) * np.trapezoid(integ, t, axis=-1)


def _vbisect(func, lo, hi, iters=70):
    """Векторная бисекция корня монотонной func на [lo,hi] (func>0 слева от корня
    для убывающей; работает и для возрастающей — сходится к смене знака)."""
    lo = np.array(lo, dtype=float); hi = np.array(hi, dtype=float)
    lo, hi = np.broadcast_arrays(lo, hi)
    lo, hi = lo.copy(), hi.copy()
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        pos = func(mid) > 0.0
        lo = np.where(pos, mid, lo)
        hi = np.where(pos, hi, mid)
    return 0.5 * (lo + hi)


def solve_Tpeak(omega_rpm, R_mm, H_mm, p, audit=False):
    omega_rpm = np.asarray(omega_rpm, dtype=float)
    R = np.asarray(R_mm, dtype=float) * 1e-3
    H = np.asarray(H_mm, dtype=float) * 1e-3
    w = omega_rpm * 2.0 * math.pi / 60.0
    sref = p["sigma_ref"] * 1e6
    Tref, m, k, T0 = p["T_ref"], p["m"], p["k"], p["T0"]
    Tsol = p["T_solidus"]
    C_emp = p.get("C_emp", None)
    eta = p.get("eta", 1.0)
    mu = p.get("mu", 0.5)
    mu_tab = p.get("mu_tab")
    use_mu_tdep = bool(p.get("use_mu_tdep"))
    F = p.get("F", 0.0)
    # --- форс-контролируемый процесс: давление и контактное касательное напряжение ---
    # контактный радиус Rc = R (передан как R_eff для shouldered); p_контакт = F/(π Rc²)
    area = math.pi * np.maximum(R, 1e-9) ** 2
    p_contact = F / area                              # Па
    # кольцевой случай (брусок в отверстии шайбы): доля f_shoe для отвода ВВЕРХ
    r_in = p.get("r_in", 0.0)
    if r_in:
        f_shoe = np.clip(1.0 - (r_in / np.maximum(R, 1e-12))**2, 0.0, 1.0)
    else:
        f_shoe = 1.0
    geom2 = R**2 + 3.0 * R * H            # геометрия только для старой эмпирической формы

    use_tdep = p.get("use_tdep")
    kt_sub, cpt_sub = p.get("kt_sub"), p.get("cpt_sub")
    cpt_dep = p.get("cpt_dep")
    kt_dep = p.get("kt_dep")           # k(T) ПРУТКА — нужна для стока в патрон
    rho_dep = p.get("rho_dep", p["rho"])
    cp_dep0 = p.get("cp_dep", p["cp"])
    v_z = p.get("v_z", 0.0)
    k2 = p.get("k2", 0.0)              # теплопроводность шайбы (отвод вверх), 0 = нет
    # объёмный расход подачи [м³/с]: задан явно (брусок) или πR²·v_z (пруток)
    feedvol = p.get("feedvol")
    if feedvol is None and p.get("use_feed"):
        feedvol = math.pi * R**2 * v_z

    # скоростная поправка (число Пекле); при T-зависимости a берётся при
    # характеристической температуре 0.75·T_solidus (Pe — второго порядка)
    Gf = 1.0
    Pe_val = np.zeros_like(np.asarray(R, dtype=float))
    if p.get("use_pe"):
        if use_tdep:
            Tc = T0 + 0.75 * (p["T_solidus"] - T0)
            k_pe = interp_prop(kt_sub, k, Tc)
            cp_pe = interp_prop(cpt_sub, p["cp"], Tc)
        else:
            k_pe, cp_pe = k, p["cp"]
        a = k_pe / (p["rho"] * cp_pe)
        Pe_val = p["v"] * R / a
        Gf = G_pe(Pe_val)

    shape = np.broadcast(omega_rpm, R, H).shape

    # --- сток в пруток (утечка в патрон) -------------------------------------
    # Стационарное 1-D поле в прутке, подаваемом К контакту со скоростью v_f,
    # дальний конец удерживается патроном на T0 при вылете L:
    #     alpha_r*T'' + v_f*T' = 0,  T(0)=T_peak,  T(L)=T0
    # Тепло, забираемое прутком у контакта = rho*cp*Vdot*(Tp-T0)/(1-exp(-Pe_L)).
    # Адвективный член rho*cp*Vdot*(Tp-T0) УЖЕ стоит в знаменателе — это ровно
    # энтальпия, возвращаемая подогретой подачей. Остаток — утечка в патрон:
    #     S_rod = rho*cp*Vdot / (exp(Pe_L) - 1),   Pe_L = v_f*L/alpha_r
    # Малая тепловая досягаемость alpha_r/v_f (сталь ~3 мм) => патрон не виден,
    # S_rod ~ 0, eta = 1. Большая (алюминий 50-220 мм) => сток реален.
    rod_L = p.get("rod_L")            # вылет прутка [мм]; None/0 = не учитывать
    def rodsink_at(T):
        if not rod_L or rod_L <= 0 or feedvol is None or not p.get("use_feed"):
            return 0.0
        k_r = interp_prop(kt_dep, p.get("k_dep", k), T) if use_tdep else p.get("k_dep", k)
        cp_d = interp_prop(cpt_dep, cp_dep0, T) if use_tdep else cp_dep0
        alpha_r = k_r / (rho_dep * cp_d)                    # м²/с
        v_f = feedvol / (math.pi * R**2) if v_z == 0.0 else v_z
        PeL = np.clip(v_f * (rod_L * 1e-3) / alpha_r, 1e-9, 700.0)
        return rho_dep * cp_d * feedvol / np.expm1(PeL)

    # --- общие функции модели (T-зависимые свойства пересчитываются на каждом шаге) ---
    def sink_at(T):
        k_c = interp_prop(kt_sub, k, T) if use_tdep else k
        cp_d = interp_prop(cpt_dep, cp_dep0, T) if use_tdep else cp_dep0
        s = 4.0 * k_c * R + 4.0 * k2 * R * f_shoe
        if p.get("use_feed") and feedvol is not None:
            s = s + rho_dep * cp_d * feedvol
        s = s + rodsink_at(T)
        return s

    def tauy_at(T):
        ratio = np.clip((T - T0) / (Tsol - T0), 0.0, None)
        return sref * np.clip(1.0 - ratio**m, 0.0, None) / SQRT3

    def mu_at(T):
        return interp_prop(mu_tab, mu, T) if (use_mu_tdep and mu_tab) else mu

    # --- старая эмпирическая форма (C_emp): монотонная бисекция по T_ref ---
    if C_emp is not None:
        def f_emp(T):
            ratio = np.clip((T - T0) / (Tref - T0), 0.0, None)
            soft = np.clip(1.0 - ratio**m, 0.0, None)
            tau = sref * soft / SQRT3
            return T0 + eta * Gf * (C_emp * 1e-4) * w * tau * geom2 - T
        res = _vbisect(f_emp, np.full(shape, float(T0)), np.full(shape, float(Tref)))
        return float(res) if res.ndim == 0 else res

    # --- физическая модель: РАСЩЕПЛЕНИЕ по переходу скольжение/залипание ---
    # τ_c = min(μ p, τ_y) — RHS имеет излом в точке T*, где μ p = τ_y(T*).
    # Ниже T*: τ_c=μ p (скольжение), Q≈const; выше: τ_c=τ_y (залипание), Q убывает.
    def Q_of_tau(tau):
        return (2.0 / 3.0) * math.pi * tau * w * R**3

    def rhs_slide(T):
        return T0 + eta * Gf * Q_of_tau(mu_at(T) * p_contact) / sink_at(T)

    def rhs_stick(T):
        return T0 + eta * Gf * Q_of_tau(tauy_at(T)) / sink_at(T)

    T0a = np.full(shape, float(T0))
    Tsa = np.full(shape, float(Tsol))
    # 1) переход T*: корень τ_y(T) − μ(T)·p (убывающая ф-ция; >0 при низких T).
    #    Если уже при T0 μp ≥ τ_y — залипание с самого начала (T*=T0).
    def gd(T):
        return tauy_at(T) - mu_at(T) * p_contact
    Tstar = _vbisect(gd, T0a, Tsa)
    Tstar = np.where(gd(T0a) <= 0.0, T0a, Tstar)
    # 2) скользящая оценка: корень rhs_slide(T)=T (clamp к солидусу, если выше)
    Tslide = _vbisect(lambda T: rhs_slide(T) - T, T0a, Tsa)
    # флаг солидуса: скользящая оценка превышает солидус (контакт у потолка плавления)
    solidus_flag = (rhs_slide(Tsa) - Tsa) > 0.0
    # 3) залипающий корень в (T*, Tsol) — монотонно, бисекция безопасна
    Tstick = _vbisect(lambda T: rhs_stick(T) - T, np.maximum(Tstar, T0a), Tsa)
    # 4) выбор ветви: скольжение, если скользящий корень ниже перехода
    sliding = Tslide <= Tstar
    Tpeak = np.minimum(np.where(sliding, Tslide, Tstick), Tsa)
    res = Tpeak

    if audit:
        T = float(res)
        muT = float(np.asarray(mu_at(T)).reshape(-1)[0]) if (use_mu_tdep and mu_tab) else mu
        tau_y = float(tauy_at(T)); tau_c = min(muT * float(p_contact), tau_y)
        k_c = float(interp_prop(kt_sub, k, T)) if use_tdep else k
        cp_d = float(interp_prop(cpt_dep, cp_dep0, T)) if use_tdep else cp_dep0
        s_cond = 4.0 * k_c * float(R)
        s_shoe = 4.0 * k2 * float(R) * float(f_shoe)
        s_adv = (rho_dep * cp_d * float(feedvol)) if (p.get("use_feed") and feedvol is not None) else 0.0
        # --- диагностика стока в пруток: НИКОГДА не должна ронять расчёт точки ---
        s_rod = 0.0; reach_mm = float("inf"); PeL_a = float("inf")
        sigma_a = 0.0; PeD_a = float("nan")
        try:
            s_rod = float(np.asarray(rodsink_at(T)).reshape(-1)[0])
            k_r_raw = p.get("k_dep")
            if k_r_raw is None:
                k_r_raw = k
            k_r_a = float(interp_prop(kt_dep, k_r_raw, T)) if use_tdep else float(k_r_raw)
            alpha_a = k_r_a / (rho_dep * cp_d)
            if v_z and v_z > 0.0:
                v_f_a = float(v_z)
            elif feedvol is not None and float(R) > 0.0:
                v_f_a = float(feedvol) / (math.pi * float(R) ** 2)
            else:
                v_f_a = 0.0
            if v_f_a > 0.0 and alpha_a > 0.0:
                reach_mm = alpha_a / v_f_a * 1e3
                # безразмерные группы, управляющие η:
                #   Pe_L = v_f*L/alpha_r  — виден ли патрон из контакта
                #   sigma = S_adv/(S_sub+S_sh+S_adv) — доля адвекции в сети стоков
                #   Pe_D = rho*cp*v_f*D/k_sub — подача против кондукции (круглый пруток)
                if rod_L:
                    PeL_a = v_f_a * (float(rod_L) * 1e-3) / alpha_a
                if k_c and float(k_c) > 0.0:
                    PeD_a = rho_dep * cp_d * v_f_a * (2.0 * float(R)) / float(k_c)
            s_net = s_cond + s_shoe + s_adv
            sigma_a = (s_adv / s_net) if s_net > 0 else 0.0
        except Exception as exc:                      # диагностика не критична
            print("[AFSD audit] rod-sink diagnostics skipped:", exc)
        s_tot = s_cond + s_shoe + s_adv + s_rod
        return T, dict(branch=("sliding" if bool(sliding) else "sticking"),
                       Pe_L=PeL_a, sigma_adv=sigma_a, Pe_D=PeD_a,
                       Tstar=float(Tstar), Tslide=float(Tslide),
                       tau_c=tau_c / 1e6, tau_y=tau_y / 1e6, mu_eff=muT,
                       p_contact=float(p_contact) / 1e6,
                       Q=float(Q_of_tau(tau_c)), sink=s_tot,
                       sink_cond=s_cond, sink_shoe=s_shoe, sink_adv=s_adv,
                       sink_rod=s_rod, rod_reach_mm=reach_mm,
                       eta_rod=(s_tot - s_rod) / s_tot if s_tot > 0 else 1.0,
                       Pe=float(np.asarray(Pe_val).reshape(-1)[0]), G=float(np.asarray(Gf).reshape(-1)[0]),
                       solidus_flag=bool(np.any(solidus_flag)), T_sol=float(Tsol))
    return float(res) if res.ndim == 0 else res


def poly_Tpeak(omega_rpm, R_mm, H_mm, c):
    w = np.asarray(omega_rpm, float); R = np.asarray(R_mm, float); H = np.asarray(H_mm, float)
    res = (c["c0"] + c["w"]*w + c["R"]*R + c["H"]*H + c["w2"]*w*w + c["R2"]*R*R
           + c["H2"]*H*H + c["wR"]*w*R + c["wH"]*w*H + c["RH"]*R*H)
    return float(res) if np.ndim(res) == 0 else res


def compute_T(omega, R, H, p, model_key):
    if model_key == "poly" and p.get("poly"):
        return poly_Tpeak(omega, R, H, p["poly"])
    if model_key == "emp" and p.get("C_emp") is not None:
        return solve_Tpeak(omega, R, H, p)
    p2 = dict(p); p2["C_emp"] = None
    return solve_Tpeak(omega, R, H, p2)


def compute_T_audit(omega, R, H, p):
    """Скаляр: (T_peak, audit-dict) физической модели — для расчёта в точке/аудита."""
    p2 = dict(p); p2["C_emp"] = None
    return solve_Tpeak(omega, R, H, p2, audit=True)


# ----------------------------------------------------------------------------
#  Модель состояния расчёта
#
#  Значения полей, режим процесса и то, какие параметры варьируются, — это не
#  свойство интерфейса, а входные данные задачи. Держим их здесь, чтобы Tk- и
#  Qt-окна считали по одному и тому же коду, а не по двум расходящимся копиям.
# ----------------------------------------------------------------------------

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

# отображаемые символы факторов в текстовом уравнении (Unicode)
UNI = {"ω": "ω", "vz": "v_f", "vx": "v_t", "D": "D", "H": "H",
       "a": "a", "F": "F", "R": "R"}

# короткое отображение в UI (списки осей, ползунки фиксированных значений)
SYM_DISP = {"vz": "v_f", "vx": "v_t"}

# значения полей по умолчанию — общий старт для обоих интерфейсов
FIELD_DEFAULTS = dict(
    eta="1.0", rod_L="0", F="8.0", mu="0.5",
    k_shoe="25", v_dep="5.0",
    w_min=200.0, w_max=1000.0, R_min=2.5, R_max=7.5, H_min=0.5, H_max=4.0,
    pt_w=500.0, pt_R=5.0, pt_H=2.0,
    vz_min=0.5, vz_max=3.0, vx_min=1.0, vx_max=10.0,
    D_min=10.0, D_max=20.0, w_bead=12.0, pt_vz=1.5, pt_vx=5.0, pt_D=15.0,
    a_min=7.0, a_max=12.0, pt_a=9.5, R_shoe=19.0,
    F_min=4.0, F_max=20.0, pt_F=8.0,
    sub_L=52.0, sub_W=32.0, sub_t=6.0, trail_len=26.0,
    rod_len=20.0, shoe_th=9.0, bar_len=16.0)

# рабочее (удерживаемое) значение каждого параметра режима
FIX_DEFAULTS = {"ω": 500.0, "R": 5.0, "H": 2.0, "vz": 1.5, "vx": 5.0,
                "D": 15.0, "a": 9.5, "F": 8.0}


def disp_sym(sym):
    """Как параметр показывается в интерфейсе."""
    return SYM_DISP.get(sym, sym)


def window_C(T_sol_C, lo=0.6, hi=0.9):
    """Границы технологического окна в °C.

    Гомологическая температура определена на АБСОЛЮТНОЙ шкале:
        T_lo = lo·T_s,  T_hi = hi·T_s,   T_s в кельвинах,
    а результат переводится обратно в °C. Прямое умножение долей на
    температуру солидуса в °C дало бы другое окно и не было бы
    гомологическим критерием."""
    if hi <= lo:                       # защита от инверсии
        lo, hi = 0.6, 0.9
    Ts_K = c_to_k(float(T_sol_C))
    return lo * Ts_K - 273.15, hi * Ts_K - 273.15


class ModelState:
    """Входные данные расчёта: поля, режим процесса, что варьируется.

    Интерфейс читает и пишет эти значения, а считают всегда методы ниже —
    поэтому Tk- и Qt-окна дают одинаковый результат по построению.
    """

    def __init__(self):
        self.materials = all_materials()
        self.mu_tables = all_mu_tables()
        pr = PRESETS[DEFAULT_PRESET]
        self.fields = {}
        for key in ("sigma_ref", "T_ref", "m", "k", "T_solidus", "T0"):
            self.fields[key] = str(pr[key])
        self.fields["C_emp"] = "" if pr["C_emp"] is None else str(pr["C_emp"])
        self.fields["rho"] = str(pr.get("rho", 2700.0))
        self.fields["cp"] = str(pr.get("cp", 900.0))
        self.fields["k_sub"] = str(pr["k"])
        self.fields["rho_sub"] = str(pr.get("rho", 2700.0))
        self.fields["cp_sub"] = str(pr.get("cp", 900.0))
        for key, val in FIELD_DEFAULTS.items():
            self.fields[key] = str(val)

        # "range" — параметр входит в матрицу и может быть осью; "fixed" — константа
        self.vary = {s: ("range" if s in ("ω", "vx") else "fixed")
                     for s in ("ω", "vz", "vx", "D", "H", "a", "F")}
        self.fix = dict(FIX_DEFAULTS)

        self.preset = DEFAULT_PRESET
        self.substrate = DEFAULT_PRESET
        self.sub_same = True
        self.shoe = SHOE_NONE
        self.bore = False
        self.mu_tdep = False
        self.mu_pair = MU_PAIR_NONE
        self.use_feedsink = True
        self.use_pe = False
        self.use_tdep = False
        self.beadw_on = False
        self.input_mode = "kin"            # "kin" (shoulderless) | "shoulder" (MELD)
        self.model_key = "phys"
        self.xaxis = "ω"
        self.yaxis = "vx"
        self.wlo, self.whi = 0.6, 0.9      # доли окна ×T_solidus

    # ---------- доступ к полям ----------
    def f(self, key, default=None):
        """Число из поля. Запятая допускается как десятичный разделитель."""
        raw = str(self.fields.get(key, "")).strip().replace(",", ".")
        if not raw:
            if default is None:
                raise ValueError("пустое поле: %s" % key)
            return default
        try:
            return float(raw)
        except ValueError:
            if default is None:
                raise
            return default

    def set(self, key, value):
        self.fields[key] = str(value)

    def load_preset(self, name):
        """Подставить свойства материала в поля прутка."""
        m = self.materials.get(name)
        if not m:
            return
        self.preset = name
        for key in ("sigma_ref", "T_ref", "m", "k", "T_solidus", "T0"):
            if key in m:
                self.fields[key] = str(m[key])
        self.fields["C_emp"] = "" if m.get("C_emp") is None else str(m["C_emp"])
        for key in ("rho", "cp"):
            if key in m:
                self.fields[key] = str(m[key])

    # ---------- параметры для решателя ----------
    def params(self):
        """Словарь p для solve_Tpeak: свойства прутка, подложки, контакта."""
        p = dict(sigma_ref=self.f("sigma_ref"), T_ref=self.f("T_ref"),
                 m=self.f("m"), T_solidus=self.f("T_solidus"), T0=self.f("T0"))
        p["rho_dep"] = self.f("rho")
        p["cp_dep"] = self.f("cp")
        if self.sub_same:
            p["k"] = self.f("k"); p["rho"] = self.f("rho"); p["cp"] = self.f("cp")
        else:
            p["k"] = self.f("k_sub"); p["rho"] = self.f("rho_sub")
            p["cp"] = self.f("cp_sub")
        c_raw = str(self.fields.get("C_emp", "")).strip().replace(",", ".")
        p["C_emp"] = float(c_raw) if c_raw else None
        p["eta"] = self.f("eta", 1.0)
        p["F"] = self.f("F") * 1e3                  # кН -> Н (форс-контроль)
        p["mu"] = self.f("mu")
        p["use_mu_tdep"] = bool(self.mu_tdep)
        p["mu_tab"] = self.mu_tables.get(self.mu_pair) if self.mu_tdep else None
        p["v"] = self.f("v_dep") * 1e-3             # мм/с -> м/с
        p["use_pe"] = bool(self.use_pe)
        dep_mat = self.materials.get(self.preset, {})
        p["poly"] = dep_mat.get("poly")
        sub_mat = dep_mat if self.sub_same else self.materials.get(self.substrate, dep_mat)
        p["kt_sub"] = sub_mat.get("kt"); p["cpt_sub"] = sub_mat.get("cpt")
        p["cpt_dep"] = dep_mat.get("cpt"); p["kt_dep"] = dep_mat.get("kt")
        p["k_dep"] = p["k"] if self.sub_same else dep_mat.get("k", p["k"])
        p["use_tdep"] = bool(self.use_tdep)
        p["rod_L"] = self.f("rod_L", 0.0)
        if self.input_mode == "shoulder" and self.shoe != SHOE_NONE:
            p["k2"] = self.f("k_shoe", 0.0)
        else:
            p["k2"] = 0.0
        return p

    # ---------- параметры режима ----------
    def candidates(self):
        """Параметры режима, доступные при текущем процессе."""
        return AX_BY_MODE[self.input_mode]

    def order(self):
        """Варьируемые параметры — по ним идут оси, матрица и регрессия."""
        return [s for s in self.candidates() if self.vary.get(s) == "range"]

    def rng(self, sym):
        return self.f(RANGE_KEYS[sym][0]), self.f(RANGE_KEYS[sym][1])

    def all_vals(self, override=None):
        """Значения всех параметров режима, с переопределением осей."""
        vals = {s: float(self.fix.get(s, 0.0)) for s in self.candidates()}
        if override:
            vals.update(override)
        return vals

    def ensure_axes(self):
        """X и Y должны быть варьируемыми и различными."""
        order = self.order()
        if not order:
            return
        if self.xaxis not in order:
            self.xaxis = order[0]
        if len(order) >= 2 and (self.yaxis not in order or self.yaxis == self.xaxis):
            self.yaxis = next(s for s in order if s != self.xaxis)

    def resolve(self, p, vals, point=False):
        """Параметры режима -> (omega, R_mm, H_mm, p_eff) для compute_T.

        Здесь процесс переводится в геометрию контакта: для shoulderless
        высота слоя следует из баланса объёма, для shouldered — эффективный
        радиус ограничен радиусом плеча."""
        F_N = vals["F"] * 1e3                          # кН -> Н
        if self.input_mode == "kin":
            R = vals["D"] / 2.0
            vz, vx = vals["vz"], vals["vx"]
            wb = self.f("w_bead") if (point and self.beadw_on) else 2.0 * R
            H = math.pi * R * R * (vz / vx) / wb        # мм
            pe = dict(p)
            pe["F"] = F_N
            pe["v"] = vx * 1e-3
            pe["v_z"] = vz * 1e-3
            pe["use_pe"] = True
            pe["use_feed"] = bool(self.use_feedsink)
            return vals["ω"], R, H, pe
        if self.input_mode == "shoulder":
            a = vals["a"]; rshoe = self.f("R_shoe")
            vz, vx, H = vals["vz"], vals["vx"], vals["H"]
            R_eff = np.minimum(a * a * vz / (2.0 * H * vx), rshoe)
            pe = dict(p)
            pe["F"] = F_N
            pe["v"] = vx * 1e-3
            pe["feedvol"] = (a * 1e-3) ** 2 * (vz * 1e-3)
            pe["use_pe"] = True
            pe["use_feed"] = bool(self.use_feedsink)
            if self.bore:
                pe["r_in"] = (a / math.sqrt(math.pi)) * 1e-3
            return vals["ω"], R_eff, H, pe
        return vals["ω"], vals["R"], vals["H"], p

    def window(self):
        """Границы технологического окна в °C для текущего солидуса."""
        return window_C(self.f("T_solidus"), self.wlo, self.whi)

    # ---------- сетка карты ----------
    def grid(self, n=140):
        """Карта T_peak по двум осям: (xN, yN, xv, yv, T, fixed)."""
        p = self.params()
        self.ensure_axes()
        order = self.order()
        if len(order) < 2:                 # для карты нужно ≥2 варьируемых
            return None
        xN, yN = self.xaxis, self.yaxis
        fixed = {s: float(self.fix[s]) for s in self.candidates() if s not in (xN, yN)}
        rx, ry = self.rng(xN), self.rng(yN)
        if rx[1] <= rx[0] or ry[1] <= ry[0]:
            return None
        xv = np.linspace(rx[0], rx[1], n)
        yv = np.linspace(ry[0], ry[1], n)
        X, Y = np.meshgrid(xv, yv)
        omega, R, H, pe = self.resolve(p, self.all_vals({xN: X, yN: Y}))
        T = compute_T(omega, R, H, pe, self.model_key)
        return xN, yN, xv, yv, T, fixed

    def point(self):
        """Расчёт в точке по полям pt_*: (T, audit, vals)."""
        p = self.params()
        vals = {s: self.f(PT_KEY[s]) for s in self.candidates()}
        omega, R, H, pe = self.resolve(p, vals, point=True)
        T, aud = compute_T_audit(omega, R, H, pe)
        return T, aud, vals

    def tau_at(self, T, p, Rc_mm=None):
        """Контактное касательное напряжение [МПа] при температуре T."""
        Tsol = p["T_solidus"]
        sy = p["sigma_ref"] * max(0.0, 1.0 - ((float(T) - p["T0"]) /
                                              (p["T_ref"] - p["T0"])) ** p["m"])
        tau_y = sy / SQRT3
        if Rc_mm:
            p_contact = p.get("F", 0.0) / (math.pi * (float(Rc_mm) * 1e-3) ** 2) / 1e6
            mu = p.get("mu", 0.5)
            if p.get("use_mu_tdep") and p.get("mu_tab"):
                mu = interp_prop(p["mu_tab"], mu, T)
            return min(mu * p_contact, tau_y)
        return tau_y

    # ---------- план эксперимента ----------
    def levels(self):
        """Уровни −1/0/+1 (min/середина/max) для варьируемых параметров."""
        order = self.order()
        lv = {}
        for s in order:
            lo, hi = self.rng(s)
            lv[s] = [lo, 0.5 * (lo + hi), hi]
        return order, lv

    def matrix_rows(self):
        """Полный план 3^N: (номер, коды, значения, τ, T_peak °C, T_peak K)."""
        p = self.params()
        order, lv = self.levels()
        if not order:
            return []
        rows, n = [], 0
        for idx in itertools.product(range(3), repeat=len(order)):
            n += 1
            vals = self.all_vals({order[j]: lv[order[j]][idx[j]]
                                  for j in range(len(order))})
            omega, R, H, pe = self.resolve(p, vals)
            T = compute_T(omega, R, H, pe, self.model_key)
            tau = self.tau_at(T, pe, R)
            rows.append((n, tuple(i - 1 for i in idx),
                         tuple(vals[s] for s in order), tau, T, c_to_k(T)))
        return rows

    def fit_regression(self):
        """МНК-полином T_peak по точкам плана: (c0, lin, quad, inter, order)."""
        p = self.params()
        order, lv = self.levels()
        N = len(order)
        if N < 1:
            return None
        F = [[] for _ in range(N)]
        for idx in itertools.product(range(3), repeat=N):
            for j in range(N):
                F[j].append(lv[order[j]][idx[j]])
        F = [np.array(c) for c in F]
        Ts = []
        for kk in range(len(F[0])):
            vals = self.all_vals({order[j]: F[j][kk] for j in range(N)})
            omega, R, H, pe = self.resolve(p, vals)
            Ts.append(float(compute_T(omega, R, H, pe, self.model_key)))
        T = np.array(Ts)
        pairs = list(itertools.combinations(range(N), 2))
        A = [np.ones_like(F[0])] + F + [F[j] * F[j] for j in range(N)]
        A += [F[a] * F[b] for a, b in pairs]
        c, *_ = np.linalg.lstsq(np.column_stack(A), T, rcond=None)
        c = [round(float(v), 6) for v in c]
        return (c[0], c[1:1 + N], c[1 + N:1 + 2 * N], c[1 + 2 * N:], order)

    # ---------- проект ----------
    def to_dict(self):
        """Состояние для сохранения в .afsd (JSON)."""
        return dict(fields=dict(self.fields),
                    vary=dict(self.vary),
                    fix={k: float(v) for k, v in self.fix.items()},
                    preset=self.preset, substrate=self.substrate,
                    sub_same=self.sub_same, shoe=self.shoe, bore=self.bore,
                    mu_tdep=self.mu_tdep, mu_pair=self.mu_pair,
                    use_feedsink=self.use_feedsink, use_pe=self.use_pe,
                    use_tdep=self.use_tdep, beadw_on=self.beadw_on,
                    input_mode=self.input_mode, model_key=self.model_key,
                    xaxis=self.xaxis, yaxis=self.yaxis,
                    wlo=self.wlo, whi=self.whi)

    def from_dict(self, d):
        """Восстановить состояние из .afsd. Неизвестные ключи игнорируются."""
        self.fields.update(d.get("fields", {}))
        self.vary.update(d.get("vary", {}))
        for k, v in (d.get("fix") or {}).items():
            try:
                self.fix[k] = float(v)
            except (TypeError, ValueError):
                pass
        for name in ("preset", "substrate", "shoe", "mu_pair",
                     "input_mode", "model_key", "xaxis", "yaxis"):
            if name in d:
                setattr(self, name, d[name])
        for name in ("sub_same", "bore", "mu_tdep", "use_feedsink",
                     "use_pe", "use_tdep", "beadw_on"):
            if name in d:
                setattr(self, name, bool(d[name]))
        for name in ("wlo", "whi"):
            if name in d:
                try:
                    setattr(self, name, float(d[name]))
                except (TypeError, ValueError):
                    pass


def poly_text(c0, lin, quad, inter, syms):
    """Полином одной строкой: T_peak = c0 + a·ω + … (² квадраты, · произведения)."""
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
        body = ("%g·%s" % (abs(coef), sym)) if sym else "%g" % abs(coef)
        if first:
            out += ("−" + body) if sign == "−" else body
            first = False
        else:
            out += " " + sign + " " + body
    return out if not first else "T_peak = 0"
