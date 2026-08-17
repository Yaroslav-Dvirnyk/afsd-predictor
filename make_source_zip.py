# -*- coding: utf-8 -*-
"""
Сборка архива с исходниками и документацией для публикации на Zenodo.

Берёт файлы, отслеживаемые git (то есть ровно то, что опубликовано в
репозитории), добавляет документацию на четырёх языках и краткие
руководства в PDF. Внутри архива — одна папка, чтобы распаковка не
рассыпала файлы по текущему каталогу.

Запуск:  python make_source_zip.py
Результат: release/AFSD_Predictor_v1.1.0_source_and_docs.zip
"""

import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.join(HERE, "release")
VERSION = "1.1.0"
NAME = "AFSD_Predictor_v%s_source_and_docs" % VERSION

# Файлы из папки release, которые кладём в архив дополнительно к исходникам:
# документация на всех языках и краткие руководства.
EXTRA = [
    "README.md", "README.ru.md", "README.uk.md", "README.zh.md",
    "AFSD_Predictor_QuickStart_en.pdf",
    "AFSD_Predictor_QuickStart_ru.pdf",
    "AFSD_Predictor_QuickStart_uk.pdf",
    "AFSD_Predictor_QuickStart_zh.pdf",
    "materials_full.json", "mu_tables_full.json",
]

# Служебные файлы репозитория, которые публиковать незачем.
SKIP = {".gitignore"}


CONTENTS = """AFSD Predictor %s — source code and documentation
=====================================================

Peak-temperature and processing-map calculator for Additive Friction Stir
Deposition (AFSD).  MIT licence.  Concept DOI 10.5281/zenodo.20669797

WHAT IS WHERE
-------------

  README.md              repository readme: how to run and build from source
  CHANGELOG.md           what changed in this release
  CITATION.cff           citation metadata
  LICENSE                MIT licence

  afsd_predictor.py      the application window (tkinter)
  afsd_core.py           physics, material database, translations, state
  afsd_plot.py           journal-style figure rendering
  user_materials.json    editable user material database
  user_mu.json           editable user friction mu(T) tables

  AFSD_Predictor.bat     Windows launcher
  AFSD_Predictor.spec    PyInstaller build description
  requirements.txt       Python dependencies
  app.ico                application icon

  make_quickstart_*.py   scripts that rebuild the illustrated quick start

  docs/README.md         user manual (English)
  docs/README.ru.md      user manual (Russian)
  docs/README.uk.md      user manual (Ukrainian)
  docs/README.zh.md      user manual (Chinese)
  docs/AFSD_Predictor_QuickStart_*.pdf
                         illustrated quick start, four languages
  docs/materials_full.json
                         all materials the program knows, as plain text
  docs/mu_tables_full.json
                         all friction mu(T) tables, as plain text

Note: README.md in the root and docs/README.md are different documents.
The first explains the code and how to build it; the second is the manual
for someone using the program.

RUNNING FROM SOURCE
-------------------

    pip install -r requirements.txt
    python afsd_predictor.py

Requires Python 3.9 or newer with tkinter, plus numpy and matplotlib.

To rebuild the Windows executable:

    pip install pyinstaller
    pyinstaller --noconfirm --clean AFSD_Predictor.spec

Yaroslav Dvirnyk, Zaporizhzhia Polytechnic National University
dvirnyk@gmail.com  ·  https://github.com/Yaroslav-Dvirnyk/afsd-predictor
""" % VERSION


def tracked_files():
    """Файлы под контролем git — то же, что видно в репозитории."""
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"],
                         cwd=HERE, capture_output=True, text=True, check=True)
    return [f for f in out.stdout.split("\n") if f.strip() and f not in SKIP]


def main():
    os.makedirs(RELEASE, exist_ok=True)
    out = os.path.join(RELEASE, NAME + ".zip")
    src = tracked_files()

    added = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in src:
            path = os.path.join(HERE, rel)
            if not os.path.exists(path):
                print("пропущен (нет файла):", rel)
                continue
            z.write(path, "%s/%s" % (NAME, rel))
            added.append(rel)
        for rel in EXTRA:
            path = os.path.join(RELEASE, rel)
            if not os.path.exists(path):
                print("пропущен (нет в release):", rel)
                continue
            # Всё из release идёт в docs/: README там — руководство
            # пользователя, а в корне лежит README репозитория (сборка,
            # структура кода). Одинаковые имена, разное назначение —
            # смешивать нельзя.
            inner = "docs/" + rel
            z.write(path, "%s/%s" % (NAME, inner))
            added.append(inner)

        z.writestr("%s/CONTENTS.txt" % NAME, CONTENTS)
        added.append("CONTENTS.txt")

    size = os.path.getsize(out)
    print("готово: %s" % out)
    print("файлов: %d, размер: %.1f МБ" % (len(added), size / 1048576.0))
    return out


if __name__ == "__main__":
    main()
