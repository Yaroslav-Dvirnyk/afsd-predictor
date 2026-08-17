# AFSD Predictor

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20669797.svg)](https://doi.org/10.5281/zenodo.20669797)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Peak-temperature and processing-map calculator for Additive Friction Stir Deposition (AFSD).**

AFSD Predictor is a desktop application that computes the **peak contact temperature**
of the Additive Friction Stir Deposition process and builds **processing maps**
(2D contour / 3D surface) over user-chosen parameters, highlighting the stability
window `0.6…0.9·T_solidus`. The model is **force-controlled**: axial force *F* and the
contact-pair friction coefficient *μ* are inputs.

It supports two configurations — **shoulderless** (round rotating rod) and
**shouldered / MELD** (square bar fed through a rotating shoulder) — an editable
material database with temperature-dependent properties, a full 3<sup>N</sup> design
matrix with least-squares regression (exportable as LaTeX), and journal-quality
figure export (PNG / PDF / SVG).

---

## Features

- **Force-controlled thermal model** with self-consistent solution and explicit
  sliding/sticking branch handling.
- **Two processes:** shoulderless (rod) and shouldered AFSD (MELD).
- **Flexible design of experiments:** each parameter can be a *range* (enters the
  3<sup>N</sup> matrix and the map axes) or a fixed *single value*.
- **Material database** (~20 built-in alloys + user materials) with editable
  temperature-dependent `k(T)` and `cₚ(T)` tables and `μ(T)` pair tables.
- **2D contour / 3D surface** maps with a configurable stability window.
- **Point evaluation** with full diagnostics (pressure, contact shear, regime, Péclet
  number, moving-source correction) and interactive labelled points on the map.
- **Design matrix + regression** equation, copyable as ready-to-paste LaTeX.
- **Journal-quality figures** — independent 2D/3D styling, vector export (PDF/SVG).
- **Projects** (`.afsd`) with unsaved-changes protection; **multilingual** UI
  (English, Українська, Русский, 中文).

## Installation

### Option A — Windows executable (no Python required)
Download `AFSD_Predictor.exe` from the [Releases](../../releases) page and run
it. The `user_materials.json` and `user_mu.json` databases are created next to
the executable on first save.

To build it yourself:

```bash
pip install pyinstaller -r requirements.txt
pyinstaller --noconfirm --clean AFSD_Predictor.spec
```

### Option B — run from source (any OS)

Requires Python 3.9+ with `tkinter` (bundled with the standard Windows/macOS
installer) and the packages below:

```bash
pip install -r requirements.txt
python afsd_predictor.py
```

On Windows you can also double-click `AFSD_Predictor.bat`.

## Quick start

1. Pick the feedstock **alloy** and the **process** (shoulderless / shouldered).
2. Set rod & substrate properties, axial force **F**, friction **μ** and efficiency **η**.
3. In **Parameter ranges**, mark which parameters vary (*range*) and which are
   fixed (*single*). A map needs at least two *range* parameters.
4. Choose the **X / Y axes** and press **▶ Plot**.
5. Use **Point evaluation** for a single point; read the **Design matrix** tab for
   the plan and the regression equation.

A complete manual is available in the application under **Help → User guide** (F1).

## The model (summary)

```
p      = F / (pi*Rc^2)
tau_y  = (sigma_ref/sqrt3)*(1 - ((T-T0)/(T_sol-T0))^m)
tau_c  = min(mu*p, tau_y)                       # contact shear
Q      = (2/3)*pi*tau_c*omega*Rc^3              # contact face only
Sink   = 4*k_sub*Rc (+ 4*k_sh*Rc shouldered) + rho_dep*cp*Vdot   # feed advection
T_peak = T0 + eta*G(Pe)*Q / Sink               # solved self-consistently
```

`eta` (0 < eta <= 1) is the single lumped heat-input efficiency, calibrated once against
a measured temperature. Two regimes follow from the `min(mu*p, tau_y)` criterion:
**sliding** (`tau_c = mu*p`, `T_peak` scales with eta) and **sticking** near the solidus
(`tau_c = tau_y`, where eta has little leverage). Conduction into the consumable rod is
deliberately absorbed into eta.

## Repository contents

| File | Description |
|------|-------------|
| `afsd_predictor.py` | The application window (tkinter). |
| `afsd_core.py` | Calculation core: physics, material database, translations, calculation state. Imports no GUI toolkit. |
| `afsd_plot.py` | Journal-style figure rendering (maps and 3D surfaces). |
| `AFSD_Predictor.bat` | Windows launcher. |
| `AFSD_Predictor.spec` | PyInstaller build description. |
| `user_materials.json` | Default material database (editable in-app). |
| `user_mu.json` | Default mu(T) pair tables (editable in-app). |
| `requirements.txt` | Python dependencies. |
| `CHANGELOG.md` | Release notes. |
| `CITATION.cff` | Citation metadata. |
| `LICENSE` | MIT license. |

The physics lives in `afsd_core.py` and the figure styling in
`afsd_plot.py`, so neither depends on the interface: the same numbers and
the same figure come out however the program is driven.

## Citation

If you use AFSD Predictor in your work, please cite the archived software:

> Dvirnyk, Y. (2026). *AFSD Predictor: peak-temperature and processing-map
> calculator for Additive Friction Stir Deposition.* Zenodo.
> https://doi.org/10.5281/zenodo.20669797

The concept DOI **10.5281/zenodo.20669797** always resolves to the latest version;
each release also has its own version DOI. See `CITATION.cff` for machine-readable
metadata.

## Author

**Yaroslav Dvirnyk** — PhD (Cand. of Sci.), Associate Professor,
Department of Aircraft Engine Technology, Zaporizhzhia Polytechnic National University.
E-mail: dvirnyk@gmail.com · ORCID: [0000-0001-5439-5413](https://orcid.org/0000-0001-5439-5413)

## License

Released under the [MIT License](LICENSE).
