# TE Measurement Desktop — Software Review (Drawbacks)

**Scope:** the full PyQt6 application in `desktop_qt/` (~8,900 lines across 36 files): instrument control, services, data, security, and every UI page and widget.
**Type:** review and documentation only. No code was changed.
**Date:** 2026-10-02 · **Version reviewed:** 1.0.0 (commit `b2ec559`)

---

## 1. Summary

The app works for **supervised, short-to-medium runs on a known-good setup**. The UI is clean, the I-V sweep runs on a proper worker thread, and the measurement maths matches the literature (Smits 1958).

It is **not yet safe or robust for unattended or multi-user use**. The gaps cluster into four areas:

1. **Heater safety depends entirely on the software staying alive.** There is no over-temperature cut-off, no close-window handling, and no hardware watchdog.
2. **Some failures turn into wrong data instead of errors.** A failed thermocouple read is stored as 0 °C. Several correction factors fall back silently.
3. **Some runs are never saved.** Runs by accounts without a lab are dropped. On a crash, records are left in the "running" state.
4. **Configuration is hard-coded or doesn't persist.** The Settings page looks editable but forgets everything on restart.

### Top 10 to fix first

| # | ID | Issue | Severity |
|---|----|-------|----------|
| 1 | SAF-1 | No over-temperature abort or independent heater cut-off | Critical |
| 2 | SAF-2 | Closing the window mid-run: no warning, no stop; a crash leaves the heater energised | Critical |
| 3 | DATA-1 | A failed thermocouple read becomes 0 °C, so a bogus ΔT and S are saved as valid data | High |
| 4 | DATA-2 | Runs by users without a lab (e.g. `superadmin`) are never saved to History | High |
| 5 | SAF-3 | Sign Out during a run neither warns nor stops the measurement | High |
| 6 | DATA-3 | A crash leaves records "running" forever and loses up to 49 unsaved rows | High |
| 7 | CALC-1 | Silent fallbacks: 4PP correction → 1.0, bad geometry → blank ρ, small ΔT → blank S | High |
| 8 | CFG-1 | Settings page doesn't persist, lists the retired 6221, and has no 2401 field | High |
| 9 | SAF-4 | A GPIB hang means ~20–25 s freezes and a worker that may never release the bus | High |
| 10 | DATA-4 | No database migrations: any model change breaks existing installs | High |

### Severity legend

- **Critical:** risk to people, samples or equipment.
- **High:** wrong or lost data, or a feature that is broken in practice.
- **Medium:** real defect with a workaround, or a latent risk.
- **Low:** polish, consistency, maintainability.

---

## 2. Backend — Safety & hardware control

**SAF-1 · No over-temperature protection or independent heater cut-off** — *Critical*
`app/instruments/session_manager.py` (measurement loop, ~L275–400)
The loop reads T1/T2 every cycle but never checks them against a maximum. The only protection is the P4K-80M current limit (ICN = 1.0 A in-plane, 1.3 A out-of-plane). Nothing caps temperature.
*Impact:* a stuck setpoint, a misplaced thermocouple, or a poorly coupled sample can overheat unchecked. There is no "T > T_max → output off" rule.

**SAF-2 · Closing the window mid-run has no handling; a crash leaves the heater on** — *Critical*
`app/ui/main_window.py` has no `closeEvent`. There is no `atexit` hook anywhere. The worker thread is created without `daemon=True` (`session_manager.py:71`).
*Impact:*
- **Normal close:** the window disappears but the non-daemon worker keeps the process alive, invisibly running the heater profile to the end. The user sees no app but the heater is still working. (Expected behaviour from the code; confirm on the bench.)
- **Crash or force-kill (Task Manager):** the `finally: output_off()` never runs, so the P4K-80M is left at its last voltage setpoint indefinitely.

**SAF-3 · Sign Out during a run neither warns nor stops it** — *High*
`app/ui/main_window.py:151–165`
`_on_logout` asks "Are you sure you want to sign out?" but doesn't check for an active measurement. It then closes the main window and opens a new login window while the worker keeps driving the heater.
*Impact:* same as SAF-2 for the normal-close case, but the heater runs headless under a different, logged-out session.

**SAF-4 · GPIB hang handling: long freezes and a worker that may never release** — *High*
VISA timeouts are 20 s (`instrument.py:72, 328, 465, 652`). Stop waits `join(timeout=25)` (`session_manager.py:49, 92, 111`).
*Impact:* a pulled cable or hung instrument blocks Stop for up to ~25 s with no feedback. If the worker is still stuck after that, it stays alive holding the VISA sessions, so the next Connect fails until the app (or sometimes the instrument) is restarted.

**SAF-5 · Silent `except: pass` in heater shutdown and disconnect paths** — *High*
`app/instruments/instrument.py` (e.g. ~L65, 174, 205, 322, 460)
Failures to send `SW0` or `VCN 0`, or to close a session, are swallowed.
*Impact:* if switching the heater off fails, nobody is told. The UI reports a clean stop while the supply may still be outputting.

**SAF-6 · Shared VISA objects have no lock (latent risk)** — *Medium*
`SeebeckSystem` instruments (`instrument.py` ~L760+) are used by the worker thread. Only `session_data` is protected by a lock (`session_manager.py`).
*Impact:* safe today because only the worker talks to the instruments during a run. Any future feature that queries an instrument from the UI mid-run (live readout, a "test connection" button) would interleave GPIB commands and corrupt replies.

**SAF-7 · No confirmation before applying heater power** — *Low*
`app/ui/pages/seebeck_page.py:724` (`_start`)
Start begins the heater profile immediately. The current is bounded by the profile editor's cap (`CURRENT_CAP_A`, L614/681) and the ICN hardware limit, so the risk is accidental starts rather than over-current.

---

## 3. Backend — Data integrity & persistence

**DATA-1 · A failed thermocouple read is stored as 0 °C** — *High*
`app/instruments/session_manager.py:319–321`
```python
t1 = result["Temp1_C"] if result["Temp1_C"] is not None else 0.0
t2 = result["Temp2_C"] if result["Temp2_C"] is not None else 0.0
delta_t = t2 - t1
```
*Impact:* one dropped 2700 reading at room temperature gives ΔT ≈ 25 °C, and an S computed from it. The row is saved, plotted and exported as valid data. It should be flagged or skipped, not zero-filled.

**DATA-2 · Runs by users with no lab are never saved** — *High*
`app/instruments/session_manager.py:219` and `app/services/measurement_service.py:245`
Both only create the DB record `if user_id is not None and lab_id is not None`. The seeded `superadmin` has `lab = None` (`app/core/database.py:57–64`).
*Impact:* a Seebeck or I-V run performed while logged in as `superadmin` never appears in History. The user isn't told; the data exists only if they exported it manually.

**DATA-3 · Crash mid-run: "running" records forever and partial row loss** — *High*
`session_manager.py:226, 353–366, 430` and `measurement_service.py:255, 371`
The record is created as `running`. Rows are committed only every 50 points. The status becomes `finished`/`error` only at the end. On I-V, an exception before finalisation leaves it `running`.
*Impact:* History accumulates runs stuck at "running" that can't be told apart from a live run, and the last ≤49 rows of a crashed Seebeck run are lost.

**DATA-4 · No schema migrations** — *High*
`app/core/database.py:44–49` uses `metadata.create_all()`, which only creates missing tables.
*Impact:* adding or renaming a column in `db_models.py` won't update existing `te_measurement.db` files. After an upgrade, queries fail or columns are missing on lab PCs. Currently the only fix is deleting the database.

**DATA-5 · DB save failure doesn't stop or warn** — *Medium*
`app/services/measurement_service.py` (~L245–290)
If creating the Measurement record fails (disk full, schema mismatch, locked file), the error is logged and the sweep continues with `db = None`.
*Impact:* the user believes the run is saved; it isn't.

**DATA-6 · No integrity hash for Seebeck runs** — *Low*
I-V results store a SHA-256 hash (`history_page.py` ~L190–204); Seebeck results don't. Data-integrity checks are inconsistent between the two methods.

---

## 4. Backend — Measurement & calculation correctness

**CALC-1 · Silent fallbacks produce plausible-looking but uncorrected results** — *High*
`app/services/measurement_service.py` (`collinear_4pp_size_factor` ~L395–434, `_enrich_point` ~L437–484), `session_manager.py:326–330`
- **4PP correction:** if the probe array doesn't fit (`length ≤ 3·s`) or a dimension is missing, CF silently becomes 1.0. The result looks normal but is uncorrected.
- **Geometry:** a zero or negative thickness or width gives ρ = blank, with no message.
- **Seebeck:** |ΔT| < 0.01 °C gives S = blank, with no reason recorded.

*Impact:* users can't tell "corrected" from "fallback" values, or "measured" from "skipped" ones.

**CALC-2 · Unusual ΔT sign convention; out-of-plane polarity fixed by editing code** — *Medium*
`app/instruments/instrument.py:16–24` and `session_manager.py:321`
ΔT is defined as T2 − T1 with T1 = hot, so ΔT is negative during heating. If an out-of-plane run shows the wrong sign, the documented fix is to swap two constants in source.
*Impact:* the sign of S depends on wiring plus this convention, and nothing checks it. The negative ΔT on screen confuses users. Correcting polarity requires a code edit and a rebuild.

**CALC-3 · No outlier rejection in the Seebeck fit** — *Medium*
`app/instruments/seebeck_analysis.py:7–27`
Plain least-squares with no robust or sigma-clipped option.
*Impact:* a single EMI spike or bad TC read (see DATA-1) biases S for its whole temperature bin.

**CALC-4 · Weak ohmic check on few points** — *Low*
`measurement_service.py` (`_linear_fit_resistance` ~L114–147)
R² on very few points (e.g. 2–3) is trivially high. There's no minimum point count or residual check behind the "ohmic" verdict.

---

## 5. Backend — Security & access control

**SEC-1 · Development accounts seeded on every launch** — *Known / accepted for now*
`app/core/database.py:57–104`, called from `init_db()` (L48).
`superadmin/superadmin`, `labadmin/labadmin` and `researcher/researcher` are recreated if missing. Acceptable in testing mode. Must be gated (env flag or first-run setup) before shared deployment.

**SEC-2 · Roles are enforced only by hiding UI; the DB is an open file** — *Medium*
`app/ui/main_window.py` (`_make_page`: Users page only for `super_admin`)
Service functions don't check the caller's role. The SQLite file in `%APPDATA%` is unencrypted and writable by anyone with OS access.
*Impact:* acceptable for a single-PC desktop tool, but role separation can't be relied on against a determined user.

**SEC-3 · Weak password policy** — *Medium*
The Settings change-password form requires ≥ 6 characters (`settings_page.py` ~L208). User creation (`users_page.py` ~L158–184) and `auth_service.change_password` have **no** rules at all.

**SEC-4 · No login throttling or lockout** — *Medium*
`app/services/auth_service.py:21–39` logs failed logins but allows unlimited attempts.

**SEC-5 · Admin can lock everyone out** — *Medium*
`app/ui/pages/users_page.py` (~L186–221)
Nothing prevents a super_admin from deactivating themselves or the last super_admin. (There's no delete, only deactivate.)

**SEC-6 · No audit trail of account changes** — *Low*
Creating users and changing roles or active flags isn't logged.

**SEC-7 · No idle lock** — *Low*
The session never times out. An unattended logged-in PC gives full access.

---

## 6. Backend — Configuration & maintainability

**CFG-1 · Settings page is misleading and incomplete** — *High*
`app/ui/pages/settings_page.py:116–133`
- Saving only overwrites module constants in memory (`setattr(instr_module, ...)`), even though the message says *"Restart the application to make them permanent"*. A restart actually **reverts** them.
- The list still contains **Keithley 6221** (retired) and has **no entry for the Keithley 2401** (`ADDR_2401`), so the I-V instrument's address can't be changed.
- *(uncertain)* Instrument objects already created hold their own `resource_name`, so a changed constant may not apply until the next `SeebeckSystem` is built.

**CFG-2 · Everything hardware-specific is hard-coded** — *Medium*
- GPIB addresses, 2700 channels, heater limits: `instrument.py:9–54`
- Optris SDK paths: `ir_camera_service.py`, `prereqs.py:25–27`
- Database location: `paths.py:7–18`
- Stagger delay: `session_manager.py` (`sleep(0.05)`)

*Impact:* any rewiring, second rig or non-standard install needs a source edit and a rebuild.

**CFG-3 · Instrument address maps duplicated in 3–4 places** — *Medium*
`dashboard.py:260–265`, `sidebar.py:31–36`, `settings_page.py:60–65`, `instrument.py:9–14`
They have already diverged (see UI-3).

**CFG-4 · Dead legacy code for the retired Keithley 6221** — *Medium*
`instrument.py:447` (`class Keithley6221`), `:771` (`self.k6221`), `:931` (`prepare_iv_4probe`), `:980` (`measure_resistivity`).
These are never connected (I-V now uses the 2401) but are still callable.
*Impact:* confusing to maintain; calling them fails with "not connected".

---

## 7. UI — Responsiveness & performance

**UI-1 · GPIB scan on the GUI thread at startup (twice)** — *Medium*
`app/ui/pages/dashboard.py:166, 255–275` and `app/ui/widgets/sidebar.py:68, 232–247`
Both create a `pyvisa.ResourceManager()` and call `list_resources()` on the main thread. The dashboard's comment calls this "non-blocking", but it blocks.
*Impact:* the window freezes for as long as the GPIB scan takes, twice. The status dots and badges are checked **once** and never refresh. They also only mean "address visible on the bus", not "instrument responding".

**UI-2 · Live Seebeck charts re-plot the full history every second** — *Medium*
`app/ui/pages/seebeck_page.py:109` (1 s timer), `:853–915` (`_refresh_charts`)
Every tick passes all points to every curve. `self._data` grows without limit.
*Impact:* fine for typical runs; on multi-hour runs, redraw cost and memory grow linearly and the UI gets sluggish. (Using `pyqtgraph` with downsampling, or appending incrementally, would bound this.)

**UI-3 · History list loads synchronously** — *Low*
`app/ui/pages/history_page.py:62–93`
The query and table fill run on the GUI thread (capped at 200 rows, no paging).

---

## 8. UI — Measurement workflow & feedback

**UI-4 · Out-of-date instrument names on the Dashboard** — *Medium*
`dashboard.py:221, 263`
The dashboard shows **"PK160"** while the sidebar and settings say "PK4-80M". It shows **"Keithley 6221"**, whose badge actually checks GPIB 24, which is now the **Keithley 2401**.
*Impact:* users see the wrong instrument named as online or offline.

**UI-5 · I-V Abort can't interrupt a hung instrument** — *Medium*
`app/ui/pages/iv_page.py:621`
Abort sets a flag the worker checks between points. A blocked VISA read (20 s timeout) can't be interrupted.

**UI-6 · Errors mid-run are hard to see or diagnose** — *Medium*
- **Seebeck:** an error only shows as a phase/status string (`seebeck_page.py` `_poll`).
- **I-V:** shows a dismissible message box.
- **Both:** there's no per-instrument "which device failed" indicator, and no record on the run of why it ended.

**UI-7 · Run metadata is optional and unvalidated** — *Medium*
`seebeck_page.py:739`, `iv_page.py:607–609`
Sample ID and operator can be empty. History then fills with unidentifiable runs, and you can't filter or search by sample.

**UI-8 · Geometry inputs allow near-zero values without feedback** — *Medium*
`iv_page.py:578–581, 664–690`
Tiny or zero dimensions become `None` and ρ is just blank, with no inline error. CF shows "—" with no reason (see CALC-1).

---

## 9. UI — Data handling & export

**UI-9 · Export code duplicated 4–5 times** — *Medium*
PNG, CSV and Excel export (including the Pillow chart embedding) is reimplemented in `seebeck_page.py` (~L959–1070), `iv_page.py` (~L779–868) and `history_page.py` (~L350–378, 607–618).
*Impact:* fixes don't propagate, and behaviour and error messages differ between pages.

**UI-10 · Pillow dependency found only at export time** — *Low*
The chart-in-Excel export discovers a missing Pillow only after the user has picked a file.

**UI-11 · I-V chart has no forward/reverse legend** — *Low*
`iv_page.py` (~L476–482)
Teal = forward and orange = reverse is shown only by colour, so exported or printed charts are ambiguous.

---

## 10. UI — Usability, consistency & accessibility

**UI-12 · Fixed pixel sizes** — *Medium*
`login_window.py:22` (420×500), `measurement_setup_dialog.py:31` (560×560), `users_page.py:24`, splitter sizes in `iv_page.py:178`.
*Impact:* can clip or crowd at 125–150 % Windows scaling or on small laptop screens.

**UI-13 · Hard-coded colours bypass the theme** — *Low*
Examples: `login_window.py:130–131`, `header_bar.py:147–150`, `dashboard.py:92`, `main_window.py:81–88`, `seebeck_page.py`, `waveform_widget.py`.
*Impact:* palette changes or a future dark mode will miss these.

**UI-14 · Colour-only cues** — *Low*
Instrument status dots and forward/reverse series rely only on colour, which is hard for colour-blind users.

**UI-15 · Few tooltips and shortcuts** — *Low*
- No tooltips on table headers (ΔT/T₀, T₀ [K]) or GPIB fields.
- Only one shortcut (Ctrl+\ toggles the sidebar).
- No Start/Stop/Export shortcuts.
- Login has no show-password toggle.

**UI-16 · Minor leftovers** — *Low*
- An unused `QSizePolicy` import (`login_window.py:8`).
- The "Coming soon" placeholder page fallback in `main_window.py`.

---

## 11. Code quality & testing

**CODE-1 · Almost no automated tests** — *Medium*
Only `tests_interval/run_interval_smoke_test.py` (timing). There are **no** tests for:
- resistivity formulas, the Smits CF, or thickness corrections
- the Seebeck calculation
- authentication
- persistence

*Impact:* regressions in the physics or the data path go unnoticed.

**CODE-2 · Very large functions and files** — *Low*
- `_run_session` is about 300 lines mixing instrument control, maths, DB writes and state (`session_manager.py:165–473`).
- `seebeck_page.py` is 1,076 lines; `history_page.py` 681; `iv_page.py` 868.
- The resistivity maths is duplicated inline in `iv_page._update_metric_cards`, separate from the service's `_enrich_point`.

*Impact:* hard to test, and the two copies of the formula can drift apart.

---

## 12. Reviewed and rejected or downgraded

These were raised during review but don't hold up against the code:

| Claim | Verdict |
|-------|---------|
| "Navigating to another page mid-run loses data / kills the run" | **Rejected.** Pages are cached in a `QStackedWidget` (`main_window._get_page`), so navigation is safe. Only *closing the window* or *signing out* is a problem (SAF-2, SAF-3). |
| "User can set heater current above hardware limits" | **Downgraded to Low (SAF-7).** The profile editor clamps to `CURRENT_CAP_A`, and the ICN current limit is set at heater initialisation. |
| "Seebeck sign is inverted" | **Downgraded to Medium (CALC-2).** Constantan measured with the expected negative sign. The issue is the confusing convention and the source-edit fix, not a proven wrong sign. |
| "Session timer misleads users into auto-logout" | **Rejected.** There is no auto-logout (that gap is SEC-7). |
| "Float precision in stored JSON corrupts data" | **Rejected.** Full-precision storage is correct; rounding is a display concern. |
| "`sleep(0.1)` loops waste CPU" | **Rejected.** The cost is negligible, and the loop keeps Stop responsive. |
| "Unbounded data will crash the app (OOM)" | **Downgraded to Medium (UI-2).** Realistic runs are thousands of points; the effect is gradual slowdown, not a crash. |

---

## 13. What's working well

- The I-V sweep runs on a `QThread` with progress and abort, so the UI stays responsive.
- The Seebeck worker runs off the GUI thread and the page polls a snapshot, a sound pattern.
- The IR camera is isolated in a separate process, so SDK crashes can't take the app down.
- The P4K-80M remote re-assertion (REN + SW1 before each VCN) is handled correctly.
- The 4PP formula and its correction factors match Smits (1958) to 0.16 %.
- bcrypt password hashing, SQLite WAL mode, foreign keys, and an I-V SHA-256 integrity hash.
- File logging to `%APPDATA%\TEMeasurement\app.log`, with uncaught exceptions captured.
- Prerequisite checks for NI-VISA and Optris at both install time and runtime.
