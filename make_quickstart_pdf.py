# -*- coding: utf-8 -*-
"""
Сборка иллюстрированного краткого руководства (PDF) для AFSD Predictor.

Скриншоты снимаются с живого окна программы, а не рисуются вручную:
руководство обязано показывать то, что пользователь реально увидит.
Поверх снимков накладываются выноски со стрелками, а панель инструментов
разбирается по кнопкам — с их настоящими значками и подписями.

Запуск:  python make_quickstart_pdf.py [ru|en|uk|zh]
Результат: release/AFSD_Predictor_QuickStart_<lang>.pdf
"""

import os
import sys
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch, Rectangle, FancyBboxPatch
import matplotlib.image as mpimg

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "release")
SHOTS = os.path.join(HERE, "build", "quickstart_shots")

# Страница A4 в альбомной ориентации: снимки окна широкие
PAGE = (11.69, 8.27)

ACCENT = "#1565c0"
INK = "#16202e"
DIM = "#5f6b80"
CALL = "#c02434"          # цвет выносок


# ---------------------------------------------------------------------------
#  тексты
# ---------------------------------------------------------------------------
TXT = {
    "en": {
        "title": "AFSD Predictor 1.1.0",
        "subtitle": "Illustrated quick start",
        "author": "Yaroslav Dvirnyk · Zaporizhzhia Polytechnic National University",
        "cover_note": "Peak-temperature and processing-map calculator for\n"
                      "Additive Friction Stir Deposition",
        "p_window": "The main window",
        "p_toolbar": "The toolbar above the plot",
        "p_flow": "Working order",
        "p_read": "Reading the result",
        "win_caption": "Everything you need for one calculation is on this screen: "
                       "inputs on the left, the map on the right.",
        "tb_caption": "Buttons are grouped by colour: navigation, interaction, "
                      "view, export.",
        "read_caption": "What the program tells you after Compute T_peak.",
        "flow_caption": "Seven steps from a blank window to a figure for a paper.",
        "zones": [
            ("Alloy", "Feedstock material.\nProperties below fill in\nautomatically."),
            ("Input type", "Shoulderless (rod) or\nShouldered (MELD)."),
            ("Rod properties", "Strength law, density,\nconductivity, η and μ."),
            ("Parameter ranges", "Tick what varies,\nset min / max.\nA map needs two."),
            ("Toolbar", "Navigation, view,\nexport, ► Plot."),
            ("Map", "Colour = temperature.\nDashed lines = window\nbounds."),
            ("Substrate, k, cp(T)", "Base material and\nproperty tables."),
        ],
        "steps": [
            ("1", "Pick the alloy", "Feedstock first — every property below follows from it."),
            ("2", "Choose the process", "Shoulderless (round rod) or Shouldered (MELD bar)."),
            ("3", "Check force and friction", "F in kN and μ of the contact pair are inputs, not fits."),
            ("4", "Mark what varies", "Tick two or more parameters and give each a min and a max."),
            ("5", "Choose the axes", "Which varying parameter goes on X, which on Y."),
            ("6", "Press ► Plot", "The map is drawn; the window bounds appear as dashed lines."),
            ("7", "Evaluate a point", "Fill the point column, press Compute T_peak — it lands on the map."),
        ],
        "reads": [
            ("T_peak", "Peak contact temperature, °C and K."),
            ("Window status", "IN WINDOW / BELOW / ABOVE the 0.6…0.9·T_s band."),
            ("Regime", "sliding (τc = μp) or sticking (τc = τy, near solidus)."),
            ("p, τc, μ, Q", "Contact pressure, shear, effective friction, heat input."),
            ("Pe, G", "Péclet number and the moving-source correction."),
            ("η_eq, S_rod", "Shown when the rod heat sink is on (L > 0)."),
            ("[geometry] H, w", "Layer height and bead width — outputs, not inputs."),
        ],
        "col_action": "Action",
        "col_note": "Note",
        "flow_note": "A map needs at least two varying parameters. With one, the map\ncannot be drawn, but the design matrix and the regression still apply.",
        "panel_name": "Point evaluation",
        "col_field": "Field",
        "col_meaning": "Meaning",
        "footer": "AFSD Predictor 1.1.0 — quick start",
        "page": "page",
        "tb_groups": ["Navigation", "Interaction", "View", "Export"],
        "full_guide": "Full manual: press F1 in the program, or see README.md",
    },
    "ru": {
        "title": "AFSD Predictor 1.1.0",
        "subtitle": "Иллюстрированное краткое руководство",
        "author": "Ярослав Двирнык · НУ «Запорожская политехника»",
        "cover_note": "Расчёт пиковой температуры и карт режимов\n"
                      "процесса Additive Friction Stir Deposition",
        "p_window": "Главное окно",
        "p_toolbar": "Панель инструментов над графиком",
        "p_flow": "Порядок работы",
        "p_read": "Чтение результата",
        "win_caption": "Всё для одного расчёта — на одном экране: ввод слева, карта справа.",
        "tb_caption": "Кнопки сгруппированы цветом: навигация, взаимодействие, вид, экспорт.",
        "read_caption": "Что программа сообщает после «Рассчитать T_peak».",
        "flow_caption": "Семь шагов от пустого окна до рисунка для статьи.",
        "zones": [
            ("Сплав", "Материал присадки.\nСвойства ниже\nподставляются сами."),
            ("Тип входных данных", "Shoulderless (пруток)\nили Shouldered (MELD)."),
            ("Свойства прутка", "Закон прочности, ρ, k,\nη и μ."),
            ("Диапазоны параметров", "Отметьте, что варьируется,\nзадайте мин / макс.\nДля карты нужно два."),
            ("Панель инструментов", "Навигация, вид,\nэкспорт, ► Построить."),
            ("Карта", "Цвет — температура.\nШтриховые линии —\nграницы окна."),
            ("Подложка, k, cp(T)", "Материал основания\nи таблицы свойств."),
        ],
        "steps": [
            ("1", "Выберите сплав", "Сначала присадка — от неё зависят все свойства ниже."),
            ("2", "Выберите схему", "Shoulderless (круглый пруток) или Shouldered (брусок MELD)."),
            ("3", "Проверьте F и μ", "Сила в кН и трение пары — это входные данные, а не подгонка."),
            ("4", "Отметьте варьируемые", "Два или больше параметров, каждому — мин и макс."),
            ("5", "Назначьте оси", "Какой варьируемый параметр по X, какой по Y."),
            ("6", "Нажмите ► Построить", "Строится карта; границы окна — штриховые линии."),
            ("7", "Рассчитайте точку", "Заполните столбец «точка» — она появится на карте."),
        ],
        "reads": [
            ("T_peak", "Пиковая температура контакта, °C и K."),
            ("Попадание в окно", "В ОКНЕ / НИЖЕ / ВЫШЕ полосы 0.6…0.9·T_s."),
            ("Ветвь", "sliding (τc = μp) или sticking (τc = τy, у солидуса)."),
            ("p, τc, μ, Q", "Контактное давление, напряжение, трение, тепловкладение."),
            ("Pe, G", "Число Пекле и скоростная поправка."),
            ("η_экв, S_rod", "Показаны, когда включён сток в патрон (L > 0)."),
            ("[геометрия] H, w", "Высота слоя и ширина валика — это выход, не вход."),
        ],
        "col_action": "Действие",
        "col_note": "Примечание",
        "flow_note": "Для карты нужно не менее двух варьируемых параметров. При одном\nкарта не строится, но матрица планирования и регрессия остаются в силе.",
        "panel_name": "Расчёт точки",
        "col_field": "Поле",
        "col_meaning": "Что означает",
        "footer": "AFSD Predictor 1.1.0 — краткое руководство",
        "page": "стр.",
        "tb_groups": ["Навигация", "Взаимодействие", "Вид", "Экспорт"],
        "full_guide": "Полное руководство: клавиша F1 в программе или README.md",
    },
    "uk": {
        "title": "AFSD Predictor 1.1.0",
        "subtitle": "Ілюстрований короткий посібник",
        "author": "Ярослав Двірник · НУ «Запорізька політехніка»",
        "cover_note": "Розрахунок пікової температури та карт режимів\n"
                      "процесу Additive Friction Stir Deposition",
        "p_window": "Головне вікно",
        "p_toolbar": "Панель інструментів над графіком",
        "p_flow": "Порядок роботи",
        "p_read": "Читання результату",
        "win_caption": "Усе для одного розрахунку — на одному екрані: ввід ліворуч, карта праворуч.",
        "tb_caption": "Кнопки згруповано кольором: навігація, взаємодія, вигляд, експорт.",
        "read_caption": "Що програма повідомляє після «Розрахувати T_peak».",
        "flow_caption": "Сім кроків від порожнього вікна до рисунка для статті.",
        "zones": [
            ("Сплав", "Матеріал присадки.\nВластивості нижче\nпідставляються самі."),
            ("Тип вхідних даних", "Shoulderless (пруток)\nабо Shouldered (MELD)."),
            ("Властивості прутка", "Закон міцності, ρ, k,\nη та μ."),
            ("Діапазони параметрів", "Позначте, що варіюється,\nзадайте мін / макс.\nДля карти потрібно два."),
            ("Панель інструментів", "Навігація, вигляд,\nекспорт, ► Побудувати."),
            ("Карта", "Колір — температура.\nШтрихові лінії —\nмежі вікна."),
            ("Підкладка, k, cp(T)", "Матеріал основи\nта таблиці властивостей."),
        ],
        "steps": [
            ("1", "Оберіть сплав", "Спершу присадка — від неї залежать усі властивості нижче."),
            ("2", "Оберіть схему", "Shoulderless (круглий пруток) або Shouldered (брусок MELD)."),
            ("3", "Перевірте F і μ", "Сила в кН і тертя пари — це вхідні дані, а не підгонка."),
            ("4", "Позначте варійовані", "Два чи більше параметрів, кожному — мін і макс."),
            ("5", "Призначте осі", "Який варійований параметр по X, який по Y."),
            ("6", "Натисніть ► Побудувати", "Будується карта; межі вікна — штрихові лінії."),
            ("7", "Розрахуйте точку", "Заповніть стовпець «точка» — вона з'явиться на карті."),
        ],
        "reads": [
            ("T_peak", "Пікова температура контакту, °C і K."),
            ("Влучання у вікно", "У ВІКНІ / НИЖЧЕ / ВИЩЕ смуги 0.6…0.9·T_s."),
            ("Гілка", "sliding (τc = μp) або sticking (τc = τy, біля солідусу)."),
            ("p, τc, μ, Q", "Контактний тиск, напруження, тертя, тепловкладення."),
            ("Pe, G", "Число Пекле та швидкісна поправка."),
            ("η_екв, S_rod", "Показані, коли увімкнено стік у патрон (L > 0)."),
            ("[геометрія] H, w", "Висота шару та ширина валика — це вихід, не вхід."),
        ],
        "col_action": "Дія",
        "col_note": "Примітка",
        "flow_note": "Для карти потрібно щонайменше два варійовані параметри. За одного\nкарта не будується, але матриця планування й регресія лишаються чинними.",
        "panel_name": "Розрахунок точки",
        "col_field": "Поле",
        "col_meaning": "Що означає",
        "footer": "AFSD Predictor 1.1.0 — короткий посібник",
        "page": "стор.",
        "tb_groups": ["Навігація", "Взаємодія", "Вигляд", "Експорт"],
        "full_guide": "Повний посібник: клавіша F1 у програмі або README.uk.md",
    },
    "zh": {
        "title": "AFSD Predictor 1.1.0",
        "subtitle": "图解快速入门",
        "author": "Yaroslav Dvirnyk · 扎波罗热国立理工大学",
        "cover_note": "搅拌摩擦增材制造（AFSD）\n峰值温度与工艺窗口计算程序",
        "p_window": "主窗口",
        "p_toolbar": "图形上方的工具栏",
        "p_flow": "操作顺序",
        "p_read": "结果解读",
        "win_caption": "一次计算所需的一切都在这一屏：左侧输入，右侧云图。",
        "tb_caption": "按钮按颜色分组：导航、交互、视图、导出。",
        "read_caption": "点击「计算 T_peak」后程序给出的信息。",
        "flow_caption": "从空白窗口到论文插图的七个步骤。",
        "zones": [
            ("合金", "填充材料。\n下方物性会\n自动填入。"),
            ("工艺形式", "无轴肩（棒材）\n或有轴肩（MELD）。"),
            ("棒材物性", "强度模型、ρ、k、\nη 与 μ。"),
            ("参数范围", "勾选变化的参数，\n填写最小/最大值。\n云图至少需要两个。"),
            ("工具栏", "导航、视图、\n导出、「绘制」。"),
            ("云图", "颜色表示温度。\n虚线为窗口边界。"),
            ("基板与 k、cp(T)", "基体材料与\n物性表。"),
        ],
        "steps": [
            ("1", "选择合金", "先定填充材料——下方所有物性都随之确定。"),
            ("2", "选择工艺形式", "无轴肩（圆棒）或有轴肩（MELD 方棒）。"),
            ("3", "核对 F 与 μ", "轴向力（kN）与摩擦副系数是输入量，而非拟合结果。"),
            ("4", "勾选变化参数", "至少两个，并为每个填写最小值与最大值。"),
            ("5", "指定坐标轴", "哪个变化参数作 X 轴，哪个作 Y 轴。"),
            ("6", "点击「绘制」", "生成云图；窗口边界以虚线表示。"),
            ("7", "计算工作点", "填写「点」一列，该点会标注在云图上。"),
        ],
        "reads": [
            ("T_peak", "接触界面峰值温度，°C 与 K。"),
            ("窗口判定", "在窗口内 / 低于 / 高于 0.6…0.9·T_s 区间。"),
            ("接触状态", "滑动（τc = μp）或粘着（τc = τy，接近固相线）。"),
            ("p、τc、μ、Q", "接触压力、剪应力、等效摩擦系数、热输入。"),
            ("Pe、G", "贝克莱数与移动热源修正。"),
            ("η_等效、S_rod", "启用棒材热流通道（L > 0）时显示。"),
            ("[几何] H、w", "层高与焊道宽度——是输出量，不是输入量。"),
        ],
        "col_action": "操作",
        "col_note": "说明",
        "flow_note": "绘制云图至少需要两个变化参数。只有一个时无法绘图，\n但试验设计矩阵与回归方程仍然有效。",
        "panel_name": "单点计算",
        "col_field": "字段",
        "col_meaning": "含义",
        "footer": "AFSD Predictor 1.1.0 — 快速入门",
        "page": "第",
        "tb_groups": ["导航", "交互", "视图", "导出"],
        "full_guide": "完整说明：程序内按 F1，或参阅 README.zh.md",
    },
}

# Панель инструментов: значок, ключ подписи, группа, цвет фона — как в программе
TOOLBAR = [
    ("🏠", {"en": "Reset",      "ru": "Сброс",      "uk": "Скидання",  "zh": "复位"},
     0, "#dbe7f5", {"en": "Back to the full view",
                    "ru": "Вернуться к полному виду",
                    "uk": "Повернутися до повного вигляду",
                    "zh": "回到完整视图"}),
    ("◄", {"en": "Back",       "ru": "Назад",      "uk": "Назад",     "zh": "后退"},
     0, "#dbe7f5", {"en": "Previous zoom state",
                    "ru": "Предыдущий масштаб",
                    "uk": "Попередній масштаб",
                    "zh": "上一个缩放状态"}),
    ("►", {"en": "Fwd",        "ru": "Вперёд",     "uk": "Уперед",    "zh": "前进"},
     0, "#dbe7f5", {"en": "Next zoom state",
                    "ru": "Следующий масштаб",
                    "uk": "Наступний масштаб",
                    "zh": "下一个缩放状态"}),
    ("✋", {"en": "Pan",        "ru": "Сдвиг",      "uk": "Зсув",      "zh": "平移"},
     1, "#e6dcf2", {"en": "Drag the map with the mouse",
                    "ru": "Тянуть карту мышью",
                    "uk": "Тягнути карту мишею",
                    "zh": "用鼠标拖动云图"}),
    ("🔍", {"en": "Zoom",       "ru": "Лупа",       "uk": "Лупа",      "zh": "缩放"},
     1, "#e6dcf2", {"en": "Zoom into a rectangle",
                    "ru": "Приблизить прямоугольник",
                    "uk": "Наблизити прямокутник",
                    "zh": "框选区域放大"}),
    ("⚙", {"en": "Margins",    "ru": "Поля",       "uk": "Поля",      "zh": "边距"},
     1, "#e6dcf2", {"en": "Adjust the plot margins",
                    "ru": "Настроить поля графика",
                    "uk": "Налаштувати поля графіка",
                    "zh": "调整绘图边距"}),
    ("🧹", {"en": "Clear",      "ru": "Очистить",   "uk": "Очистити",  "zh": "清除"},
     1, "#e6dcf2", {"en": "Remove all marked points",
                    "ru": "Убрать все нанесённые точки",
                    "uk": "Прибрати всі нанесені точки",
                    "zh": "清除全部标记点"}),
    ("▦", {"en": "2D contour", "ru": "2D карта",   "uk": "2D карта",  "zh": "二维云图"},
     2, "#fdeccb", {"en": "Contour map",
                    "ru": "Контурная карта",
                    "uk": "Контурна карта",
                    "zh": "等值线云图"}),
    ("◳", {"en": "3D surface", "ru": "3D поверхность", "uk": "3D поверхня", "zh": "三维曲面"},
     2, "#fdeccb", {"en": "Surface plot",
                    "ru": "Поверхность",
                    "uk": "Поверхня",
                    "zh": "曲面图"}),
    ("🖼", {"en": "PNG", "ru": "PNG", "uk": "PNG", "zh": "PNG"},
     3, "#dcefdc", {"en": "Raster image (Ctrl+Shift+P)",
                    "ru": "Растровый рисунок (Ctrl+Shift+P)",
                    "uk": "Растровий рисунок (Ctrl+Shift+P)",
                    "zh": "位图（Ctrl+Shift+P）"}),
    ("📄", {"en": "PDF", "ru": "PDF", "uk": "PDF", "zh": "PDF"},
     3, "#dcefdc", {"en": "Vector, for journals (Ctrl+Shift+D)",
                    "ru": "Вектор, для журналов (Ctrl+Shift+D)",
                    "uk": "Вектор, для журналів (Ctrl+Shift+D)",
                    "zh": "矢量图，适合期刊（Ctrl+Shift+D）"}),
    ("◆", {"en": "SVG", "ru": "SVG", "uk": "SVG", "zh": "SVG"},
     3, "#dcefdc", {"en": "Vector, editable (Ctrl+Shift+G)",
                    "ru": "Вектор, редактируемый (Ctrl+Shift+G)",
                    "uk": "Вектор, редагований (Ctrl+Shift+G)",
                    "zh": "可编辑矢量图（Ctrl+Shift+G）"}),
    ("🧮", {"en": "CSV", "ru": "CSV", "uk": "CSV", "zh": "CSV"},
     3, "#dcefdc", {"en": "Grid of numbers (Ctrl+Shift+E)",
                    "ru": "Сетка чисел (Ctrl+Shift+E)",
                    "uk": "Сітка чисел (Ctrl+Shift+E)",
                    "zh": "数值网格（Ctrl+Shift+E）"}),
]


def pick_font(lang="en"):
    """Шрифт для страницы.

    Для китайского нужен шрифт с иероглифами: в Segoe UI их нет, и текст
    вышел бы пустыми квадратами. Для остальных языков хватает Segoe UI,
    в котором есть и кириллица, и нужные символы вроде τ, μ, °.
    """
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    order = (("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC",
              "Arial Unicode MS", "DejaVu Sans")
             if lang == "zh" else
             ("Segoe UI", "Arial Unicode MS", "DejaVu Sans"))
    for name in order:
        if name in have:
            return name
    return "DejaVu Sans"


def emoji_font():
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Segoe UI Emoji", "Segoe UI Symbol", "Segoe UI"):
        if name in have:
            return name
    return None


def _page(pdf, fam):
    fig = plt.figure(figsize=PAGE, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return fig, ax


def _footer(fig, ax, t, fam, n):
    ax.plot([0.06, 0.94], [0.045, 0.045], color="#d3dae6", lw=0.8)
    ax.text(0.06, 0.028, t["footer"], fontsize=8, color=DIM, family=fam)
    ax.text(0.94, 0.028, "%s %d" % (t["page"], n), fontsize=8, color=DIM,
            family=fam, ha="right")


def cover(pdf, t, fam):
    fig, ax = _page(pdf, fam)
    ax.add_patch(Rectangle((0, 0.72), 1, 0.28, color="#eef3fb", zorder=0))
    ax.text(0.08, 0.86, t["title"], fontsize=34, color=INK, family=fam, weight="bold")
    ax.text(0.08, 0.80, t["subtitle"], fontsize=17, color=ACCENT, family=fam)
    ax.text(0.08, 0.62, t["cover_note"], fontsize=13, color=INK, family=fam,
            linespacing=1.7)
    ax.text(0.08, 0.50, t["author"], fontsize=10.5, color=DIM, family=fam)
    ax.text(0.08, 0.44, "MIT licence · DOI 10.5281/zenodo.20669797",
            fontsize=10, color=DIM, family=fam)
    ax.text(0.08, 0.15, t["full_guide"], fontsize=10.5, color=ACCENT, family=fam)
    pdf.savefig(fig); plt.close(fig)


def page_window(pdf, t, fam, shot, zones_xy):
    """Скриншот окна с выносками на группы элементов."""
    fig, ax = _page(pdf, fam)
    ax.text(0.06, 0.945, t["p_window"], fontsize=20, color=INK, family=fam, weight="bold")
    ax.text(0.06, 0.912, t["win_caption"], fontsize=10.5, color=DIM, family=fam)

    if not os.path.exists(shot):
        ax.text(0.5, 0.5, "screenshot missing", ha="center", family=fam)
        pdf.savefig(fig); plt.close(fig); return

    img = mpimg.imread(shot)
    ih, iw = img.shape[0], img.shape[1]
    # Снимок занимает левые две трети листа; высоту считаем от его пропорций,
    # иначе картинка растягивается и подписи в ней плывут.
    bw = 0.615
    bh = bw * (ih / float(iw)) * (PAGE[0] / PAGE[1])
    bx, by = 0.335, 0.865 - bh
    ax_img = fig.add_axes([bx, by, bw, bh])
    ax_img.imshow(img)
    ax_img.axis("off")
    # Ось со снимком кладём НИЖЕ основной: иначе она перекрывает выноски, и
    # линии обрываются на краю окна программы вместо того, чтобы идти поверх.
    ax_img.set_zorder(1)
    ax.set_zorder(2)
    ax.patch.set_visible(False)
    box = [bx, by, bw, bh]

    n = len(t["zones"])
    top, step = 0.855, 0.112
    for i, ((fx, fy), (name, desc)) in enumerate(zip(zones_xy, t["zones"])):
        ty = top - i * step
        px = box[0] + fx * box[2]
        py = box[1] + (1.0 - fy) * box[3]
        # карточка справа: высота под заголовок и до трёх строк пояснения
        lines = desc.count(chr(10)) + 1
        ch = 0.030 + 0.019 * lines
        cy = ty - ch + 0.030
        ax.add_patch(FancyBboxPatch((0.055, cy), 0.245, ch,
                                    boxstyle="round,pad=0.005",
                                    fc="#fdf3f4", ec=CALL, lw=0.8,
                                    transform=ax.transAxes, zorder=4))
        # Выноска идёт поверх снимка, но не поперёк карты: от карточки —
        # горизонтально до правого края окна, затем ломаной к самой метке.
        edge = box[0] + box[2] + 0.012
        ax.annotate("", xy=(px, py), xycoords=ax.transAxes,
                    xytext=(0.303, cy + ch * 0.55), textcoords=ax.transAxes,
                    arrowprops=dict(arrowstyle="-|>", color=CALL, lw=1.0,
                                    alpha=0.85, shrinkA=0, shrinkB=2,
                                    connectionstyle="angle,angleA=0,angleB=90,rad=6"),
                    zorder=10)
        ax.text(0.064, cy + ch - 0.016, "%d. %s" % (i + 1, name), fontsize=9.5,
                color=CALL, family=fam, weight="bold", va="center", zorder=6)
        ax.text(0.064, cy + ch - 0.030, desc, fontsize=8, color=INK, family=fam,
                linespacing=1.45, va="top", zorder=6)
        # Номер рисуем НА оси снимка, в пикселях картинки: отдельная ось
        # всегда рисуется поверх текста основной, поэтому zorder на ax не
        # помогает — метка оказывалась под изображением.
        ax_img.text(fx * iw, fy * ih, str(i + 1), fontsize=7.5, color="white",
                    family=fam, ha="center", va="center", weight="bold",
                    zorder=30,
                    bbox=dict(boxstyle="circle,pad=0.3", fc=CALL, ec="white",
                              lw=1.2))

    _footer(fig, ax, t, fam, 2)
    pdf.savefig(fig); plt.close(fig)


def page_toolbar(pdf, t, fam, lang, shot):
    """Разбор панели инструментов: значок, подпись, назначение."""
    fig, ax = _page(pdf, fam)
    ax.text(0.06, 0.945, t["p_toolbar"], fontsize=20, color=INK, family=fam, weight="bold")
    ax.text(0.06, 0.912, t["tb_caption"], fontsize=10.5, color=DIM, family=fam)

    if os.path.exists(shot):
        img = mpimg.imread(shot)
        ax_img = fig.add_axes([0.06, 0.775, 0.88, 0.10])
        ax_img.imshow(img)
        ax_img.axis("off")
        for s in ax_img.spines.values():
            s.set_visible(True); s.set_edgecolor("#c4ccd6")

    efam = emoji_font()
    y = 0.735
    last_group = None
    for glyph, cap, group, colour, desc in TOOLBAR:
        if group != last_group:
            ax.text(0.06, y, t["tb_groups"][group], fontsize=10, color=ACCENT,
                    family=fam, weight="bold")
            y -= 0.031
            last_group = group
        ax.add_patch(FancyBboxPatch((0.075, y - 0.019), 0.038, 0.040,
                                    boxstyle="round,pad=0.004",
                                    fc=colour, ec="#b9c2cf", lw=0.7,
                                    transform=ax.transAxes))
        ax.text(0.094, y + 0.001, glyph, fontsize=13, ha="center", va="center",
                family=(efam or fam))
        ax.text(0.128, y + 0.001, cap[lang], fontsize=10.5, color=INK,
                family=fam, va="center", weight="bold")
        ax.text(0.295, y + 0.001, desc[lang], fontsize=9.5, color=DIM,
                family=fam, va="center")
        y -= 0.0405

    _footer(fig, ax, t, fam, 3)
    pdf.savefig(fig); plt.close(fig)


def page_flow(pdf, t, fam):
    """Порядок работы — таблицей, в духе технической документации."""
    fig, ax = _page(pdf, fam)
    ax.text(0.06, 0.945, t["p_flow"], fontsize=20, color=INK, family=fam, weight="bold")
    ax.text(0.06, 0.912, t["flow_caption"], fontsize=10.5, color=DIM, family=fam)

    x_num, x_act, x_desc = 0.070, 0.115, 0.360
    y = 0.835
    # шапка таблицы
    ax.text(x_num, y, "№", fontsize=9.5, color="#33415c", family=fam, weight="bold")
    ax.text(x_act, y, t["col_action"], fontsize=9.5, color="#33415c",
            family=fam, weight="bold")
    ax.text(x_desc, y, t["col_note"], fontsize=9.5, color="#33415c",
            family=fam, weight="bold")
    ax.plot([0.06, 0.94], [y - 0.016, y - 0.016], color="#8f9aa8", lw=0.9)

    y -= 0.052
    for num, head, desc in t["steps"]:
        ax.text(x_num, y, num + ".", fontsize=10.5, color=INK, family=fam,
                va="center")
        ax.text(x_act, y, head, fontsize=10.5, color=INK, family=fam,
                va="center", weight="bold")
        ax.text(x_desc, y, desc, fontsize=10, color=DIM, family=fam, va="center")
        ax.plot([0.06, 0.94], [y - 0.026, y - 0.026], color="#d7dce3", lw=0.6)
        y -= 0.062

    ax.text(0.06, y - 0.02, t["flow_note"], fontsize=9.5, color=DIM,
            family=fam, va="top", linespacing=1.6)

    _footer(fig, ax, t, fam, 4)
    pdf.savefig(fig); plt.close(fig)


def page_read(pdf, t, fam, shot):
    """Чтение результата: строка расчёта точки с расшифровкой.

    Оформлено под вид самой программы — серая рамка с заголовком, как у
    панели «Point evaluation», и обычная таблица: страница описывает
    существующее окно, а не показывает какой-то другой интерфейс.
    Строка берётся текстом из живого расчёта, потому что панель на экране
    лежит под графиком и в кадр не попадает.
    """
    fig, ax = _page(pdf, fam)
    ax.text(0.06, 0.945, t["p_read"], fontsize=20, color=INK, family=fam, weight="bold")
    ax.text(0.06, 0.912, t["read_caption"], fontsize=10.5, color=DIM, family=fam)

    line = ""
    if os.path.exists(shot):
        with open(shot, encoding="utf-8") as fh:
            line = fh.read().strip()
    if line:
        # рамка в духе ttk.LabelFrame: тонкая серая линия и подпись сверху
        ax.add_patch(Rectangle((0.06, 0.775), 0.88, 0.095, fill=False,
                               ec="#9aa4b2", lw=0.9, transform=ax.transAxes))
        ax.add_patch(Rectangle((0.075, 0.862), 0.115, 0.016, fc="white",
                               ec="none", transform=ax.transAxes, zorder=3))
        ax.text(0.080, 0.870, t["panel_name"], fontsize=8.5, color="#33415c",
                family=fam, va="center", zorder=4)
        words, rows, cur = line.split("   "), [], ""
        for wd in words:
            if len(cur) + len(wd) > 92:
                rows.append(cur); cur = wd
            else:
                cur = (cur + "   " + wd) if cur else wd
        rows.append(cur)
        # поле результата — как Entry в программе: белое, с рамкой
        ax.add_patch(Rectangle((0.075, 0.792), 0.85, 0.058, fc="white",
                               ec="#b6bec9", lw=0.8, transform=ax.transAxes))
        ax.text(0.085, 0.821, chr(10).join(rows[:2]), fontsize=9, color="#111111",
                family="DejaVu Sans", va="center", linespacing=1.7)

    # таблица расшифровки: две колонки, тонкие линейки — без цветных плашек
    y = 0.700
    ax.plot([0.06, 0.94], [y + 0.030, y + 0.030], color="#8f9aa8", lw=0.9)
    ax.text(0.070, y + 0.042, t["col_field"], fontsize=9.5, color="#33415c",
            family=fam, weight="bold")
    ax.text(0.330, y + 0.042, t["col_meaning"], fontsize=9.5, color="#33415c",
            family=fam, weight="bold")
    for name, desc in t["reads"]:
        ax.text(0.070, y, name, fontsize=10, color=INK, family=fam, va="center")
        ax.text(0.330, y, desc, fontsize=10, color=INK, family=fam, va="center")
        ax.plot([0.06, 0.94], [y - 0.024, y - 0.024], color="#d7dce3", lw=0.6)
        y -= 0.055

    ax.text(0.06, 0.135, t["full_guide"], fontsize=10.5, color=INK, family=fam)
    _footer(fig, ax, t, fam, 5)
    pdf.savefig(fig); plt.close(fig)


def build(lang="ru"):
    t = TXT[lang]
    fam = pick_font(lang)
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "AFSD_Predictor_QuickStart_%s.pdf" % lang)

    shot_win = os.path.join(SHOTS, "window.png")
    shot_tb = os.path.join(SHOTS, "toolbar.png")
    shot_pt = os.path.join(SHOTS, "result_line.txt")

    # доли (x, y) точек привязки выносок на снимке окна
    # Доли (x, y) считаны по координатной сетке, наложенной на сам снимок,
    # а не подобраны на глаз.
    zones_xy = [(0.075, 0.030), (0.075, 0.140), (0.075, 0.200),
                (0.075, 0.955), (0.330, 0.058), (0.500, 0.400), (0.075, 0.760)]

    with PdfPages(out) as pdf:
        cover(pdf, t, fam)
        page_window(pdf, t, fam, shot_win, zones_xy)
        page_toolbar(pdf, t, fam, lang, shot_tb)
        page_flow(pdf, t, fam)
        page_read(pdf, t, fam, shot_pt)
        d = pdf.infodict()
        d["Title"] = "%s — %s" % (t["title"], t["subtitle"])
        d["Author"] = "Yaroslav Dvirnyk"
        d["Subject"] = "AFSD Predictor illustrated quick start"
    print("готово:", out)
    return out


if __name__ == "__main__":
    langs = sys.argv[1:] or ["ru"]
    for lg in langs:
        build(lg)
