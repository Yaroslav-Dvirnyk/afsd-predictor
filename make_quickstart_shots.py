# -*- coding: utf-8 -*-
"""
Съёмка скриншотов для иллюстрированного руководства.

Окно программы поднимается, доводится до состояния «карта построена, точка
рассчитана», и с него снимаются три кадра: всё окно, панель инструментов и
строка результата. Снимки идут в build/quickstart_shots/.

Запуск:  python make_quickstart_shots.py [lang]
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build", "quickstart_shots")

# Экран может быть с масштабированием (например, 3840x2160 при 150 %): тогда
# координаты виджетов Tk и пиксели ImageGrab живут в разных системах, и кадры
# уезжают. Просим Windows отдавать честные пиксели ДО создания окна.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import afsd_predictor as A


def main(lang="en"):
    os.makedirs(OUT, exist_ok=True)
    app = A.App()
    app.geometry("2300x1180+15+10")
    app.update()
    app.set_language(lang)
    app.update()
    app.build()
    app.update()
    app.calc_point()
    app.update()
    app.update_idletasks()
    app.lift()
    app.focus_force()

    def grab():
        from PIL import ImageGrab
        x0, y0 = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()

        def shot(name, box):
            img = ImageGrab.grab(bbox=box)
            path = os.path.join(OUT, name)
            img.save(path)
            print("%-12s %s" % (name, img.size))

        # всё окно
        shot("window.png", (x0, y0, x0 + w, y0 + h))
        # панель инструментов над графиком: границы берём у самого виджета,
        # а не подбираем на глаз — иначе крайние кнопки срезаются
        # Панель ищем по подписи первой кнопки: рядом лежат вкладки того же
        # типа и того же цвета, поэтому ни положение, ни фон не опознают её
        # однозначно.
        bar = None
        def _find(w, depth=0):
            for ch in w.winfo_children():
                try:
                    for g in ch.winfo_children():
                        for l in g.winfo_children():
                            if l.winfo_class() == "Label" and                                     str(l.cget("text")) in ("Reset", "Сброс",
                                                            "Скидання", "复位"):
                                return ch
                except Exception:
                    pass
                if depth < 6:
                    got = _find(ch, depth + 1)
                    if got is not None:
                        return got
            return None
        bar = _find(app)
        if bar is not None:
            cells = [c for c in bar.winfo_children()
                     if c.winfo_class() == "Frame" and c.winfo_width() > 20]
            bx0 = cells[0].winfo_rootx() - 8
            bx1 = cells[-1].winfo_rootx() + cells[-1].winfo_width() + 8
            by = bar.winfo_rooty()
            shot("toolbar.png", (bx0, by, bx1, by + bar.winfo_height()))

        # Строку результата сохраняем ТЕКСТОМ, а не кадром: панель «Point
        # evaluation» лежит под графиком и на экране не отрисовывается, пока
        # график занимает всё место. Текст к тому же читается лучше мелкого
        # снимка.
        with open(os.path.join(OUT, "result_line.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write(app.result_var.get())
        print("%-12s %s" % ("result_line", "сохранена текстом"))

        app.destroy()

    app.after(1800, grab)
    app.mainloop()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "en")
