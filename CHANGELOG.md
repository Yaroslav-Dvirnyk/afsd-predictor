# Changelog

All notable changes to AFSD Predictor are documented here.
The project follows [Semantic Versioning](https://semver.org/).

## v1.1.0 — 2026-08-17

### Physics

- **Moving-source kernel corrected.** `G(Pe)` now assumes an *isothermal*
  flux distribution over the contact disc (Carslaw & Jaeger §10.4),
  `q(ρ) = Q / (2πR·√(R²−ρ²))`, consistent with the steady-state limit
  `Q/(4kR)` and with the `4kR` sink conductances. The substitution
  `s = sin(t)` removes the integrable singularity at `s = 1`, and
  `G(0) = 1` now holds identically.
- **Heat leak into the chuck along the rod.** New input *L, unsupported rod
  length [mm]* (0 = off) adds the sink
  `S_rod = ρc_p·V̇ / (exp(Pe_L) − 1)`, with `Pe_L = v_f·L/α_rod`.
  Point evaluation reports the equivalent efficiency `η_экв`, `S_rod`,
  `Pe_L` and the thermal reach `α/v_f`. The sink switches itself off for
  steels, whose reach is only a few millimetres, so the chuck is not
  "visible" from the contact.
- **Process window on the absolute scale.** The homologous temperature is a
  ratio of *absolute* temperatures, so the window is now computed as
  `frac·T_s` in kelvin and converted back to °C. Boundary labels read
  `T/T_s = 0.6 (242)` — the dimensionless ratio with its value in °C in
  brackets.
- `η` relabelled *heat-retention factor* in all four interface languages.

### Fixed

- Point evaluation crashed when the audit branch ran: `kt_dep` was not
  unpacked from the parameter dictionary.
- The audit print killed the calculation when the console was cp1251 (no
  τ/α/η characters) or absent altogether, as in a windowed build.
- Hotkeys did not reach the application once the plot had focus: the
  matplotlib canvas binds `<Key>` itself and swallowed them. Bindings are
  now duplicated onto the canvas widget, on the root and on the window,
  and each handler is wrapped so one failing callback cannot silence the
  rest.
- The design matrix disappeared whenever a map could not be drawn. A map
  needs two axes, but the 3^N plan is meaningful with a single varying
  factor, so the table and regression now refresh either way.

### Changed

- The bead width checkbox now reads *use w (affects H only)*: `w` does not
  enter the thermal balance — the volumetric feed rate `πR²v_f` does — and
  the old label invited the opposite conclusion. The field is kept as a
  diagnostic: comparing the computed `H` with a measured bead height
  validates the user's own feed, traverse and diameter inputs.
- The program starts with the plot settings used for the paper figures
  (28 pt type, 3.7:3 box aspect, fill restricted to the process window),
  so a map is publication-ready without manual adjustment.
- Figure export renders onto a fresh figure sized from the type size, so
  the exported file no longer depends on how the window is sized.

### Internal

- Split into modules: `afsd_core.py` (physics, materials, translations,
  calculation state), `afsd_plot.py` (journal-style figure rendering),
  `afsd_predictor.py` (the tkinter interface). The core imports no GUI
  toolkit, and the figure styling lives in one place, so the same numbers
  and the same figure come out however the program is driven. The split
  was verified to change neither: temperatures match to 1e-9 and the
  rendered maps are pixel-identical to the previous single-file version.

## v1.0.1 — 2026-06-12

- Application icon (window and executable).
- Zenodo DOI badge and citation metadata.

## v1.0.0 — 2026-06-12

- First release: peak-temperature and processing-map calculator for AFSD.
