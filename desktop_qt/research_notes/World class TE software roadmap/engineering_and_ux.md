# Engineering and UX for World-Class Scientific Desktop Software

## Testing Strategy for Instrument Software

### Takeaway
pytest-qt with headless Qt platforms enables reliable CI/CD-friendly GUI testing for PyQt applications; comprehensive strategy requires unit tests for physics/math, simulated instruments, and regression testing on golden files.

### Cited Findings
- pytest-qt is widely considered the go-to solution for automated GUI testing of PyQt and PySide applications in Python, with latest version 4.5.0 released July 2025 — [pytest-qt · PyPI](https://pypi.org/project/pytest-qt/)
- pytest-qt provides the qtbot fixture for simulating user interaction (key presses, mouse clicks), and automatically captures qDebug, qWarning, qCritical messages; exceptions in virtual methods and slots are captured and fail tests — [pytest-qt · PyPI](https://pypi.org/project/pytest-qt/)
- Headless testing with pytest-qt allows faster test execution, improved repeatability, and seamless CI/CD pipeline integration without physical display — [Headless Testing of PySide/PyQt GUI Applications with pytest-qt](https://ilmanzo.github.io/post/testing_pyside_gui_applications/)
- pyvisa-sim enables instrument software testing without physical hardware by simulating GPIB responses — [GPIB instrument simulation with pyvisa-sim](https://pyvisa.readthedocs.io/en/stable/)
- Golden-file regression testing captures recorded raw data from real instrument runs and compares future test outputs against these files to detect data pipeline regressions — [Regression Testing Strategies](https://en.wikipedia.org/wiki/Regression_testing)

### Inferences
- For a 1–3 person team, pytest-qt + golden-file tests on recorded GPIB datasets provide immediate ROI: catch UI layout regressions and data processing bugs without hardware (cheap, fast CI runs). Add pyvisa-sim for protocol-level unit tests on data acquisition logic.
- Property-based testing with hypothesis can generate edge-case probe temperatures and voltage ranges to catch physics calculation bugs that manual test suites miss.

### Gaps
- No specific guidance found on hypothesis strategy for thermoelectric measurement data (voltage, temperature, resistivity edge cases)
- PyMeasure expected_protocol patterns for protocol-level testing specific to Keithley SourceMeter I-V workflows not found in search results

---

## CI on GitHub Actions for Windows PyQt Apps

### Takeaway
GitHub Actions can build PyInstaller installers for Windows with QT_QPA_PLATFORM=offscreen for headless testing; aqtinstall provides silent Qt installation for CI environments.

### Cited Findings
- GitHub Actions has dedicated community actions for PyInstaller Windows builds (e.g., "PyInstaller Windows" action in GitHub Marketplace) — [PyInstaller Windows · GitHub Marketplace](https://github.com/marketplace/actions/pyinstaller-windows)
- aqtinstall is a headless alternative to the graphical Qt installer, designed for CI environments like GitHub Actions where interactive UI is not usable — [aqtinstall documentation](https://aqtinstall.readthedocs.io/)
- The "Could not find the Qt platform plugin" error when packaging PyQt6 with PyInstaller occurs because PyInstaller doesn't automatically bundle Qt plugin files; fix via --add-data in .spec file — [Fix PyInstaller Qt platform plugin error](https://www.pythonguis.com/faq/pyinstaller-4-2-pyside6/)
- Qt for Python & PyInstaller work out of the box with PyQt6 and current PyInstaller versions (compatible with Python 3.6+) — [Qt for Python & PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)
- Qt Series blog demonstrates GitHub Actions workflows for cross-platform (Linux, Windows, macOS) Qt builds — [Qt Series S01E01: GitHub Actions & Qt](https://medium.com/@bgallois/qt-series-s01e01-github-actions-qt-7be4c7fdad0f)

### Inferences
- Workflow should: (1) use aqtinstall to cache Qt 6.x binaries; (2) install Python 3.13, uv for deps; (3) run pytest with QT_QPA_PLATFORM=offscreen; (4) build PyInstaller .spec with all Qt plugins listed; (5) sign .exe (see code signing section); (6) upload to release artifacts.
- Cache Qt installation (~500MB) between CI runs to avoid 10+ minute download on every build.

### Gaps
- Specific Qt platform plugin list for thermoelectric measurement app (imageformats, platforms, etc.) not researched
- Performance benchmarks for CI times on Windows runners not found

---

## Static Analysis: Type Checking and Linting

### Takeaway
Modern Python 2025–2026 standard: Ruff for linting & formatting, Pyright for type checking, pytest for testing; all configured in pyproject.toml; mypy remains option for wide plugin ecosystem.

### Cited Findings
- In 2026, the recommended answer to type checking is pyright or mypy, and the answer to linting is overwhelmingly ruff — [Python Tooling in 2025](https://osquant.com/papers/python-tooling-in-2025/)
- Pyright (Microsoft, written in TypeScript) is fast—can re-check large files in tens of milliseconds; powers VS Code's Pylance by default — [pyright: Python Static Type Checker](https://pydevtools.com/handbook/reference/pyright/)
- mypy remains the original Python type checker with widest plugin ecosystem for specialized type stubs — [mypy: Python Static Type Checker](https://pydevtools.com/handbook/reference/mypy/)
- Ruff does NOT support type checking; use ruff for linting/formatting only, pair with Pyright or mypy for type inference — [Does Ruff support type checking?](https://pydevtools.com/handbook/explanation/does-ruff-support-type-checking/)
- Modern Python codebase rests on four pillars: package management (uv), linting & formatting (Ruff), static type checking (Pyright), testing (pytest) — all configured in single pyproject.toml file — [Python Tooling in 2025](https://osquant.com/papers/python-tooling-in-2025/)

### Inferences
- For 9k-line instrument app: start with Pyright at default strictness (catches common bugs: wrong Numpy dtypes, None access, mismatched dict key types). Gradually increase to --strict as team comfort grows.
- Ruff ruleset: start with default, add isort (import sorting), flake8-bugbear, and any domain-specific rules (e.g., pydantic for settings validation).
- Pre-commit hook: ruff check --fix, pyright --outputjson (report but don't fail on first pass to avoid false positives blocking CI).

### Gaps
- PyQt6-specific type stubs status and any gaps not found
- Integration patterns for Qt plugins with type checkers unclear

---

## Code Signing and Windows SmartScreen Reputation

### Takeaway
Azure Trusted Signing (Microsoft's modern cloud-based alternative at $9.99/month) is cheapest path to instant SmartScreen reputation, replacing legacy EV/OV certificates; available to US/Canada-based businesses with 3+ year history; restricted for non-US/Canada as of April 2025.

### Cited Findings
- Azure Trusted Signing costs $9.99/month, requires .NET 6.0+ runtime and signtool.exe v10.0.2261.755+, delivers instant reputation on all signed executables tied to verified identity — [Code Signing Windows Apps with Azure Artifact Signing](https://melatonin.dev/blog/code-signing-on-windows-with-azure-trusted-signing/)
- Azure Trusted Signing available to US, Canadian, EU, or UK businesses as of April 2026; restricted to those with 3+ years verifiable business history and requiring government ID + proof of business ownership — [Code Signing Windows Apps with Azure Artifact Signing](https://melatonin.dev/blog/code-signing-on-windows-with-azure-trusted-signing/)
- Azure Trusted Signing is described as modern equivalent to EV certs, making EV/OV certificates legacy; avoids third-party CAs entirely — [Code signing options for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- PyInstaller does NOT sign executables automatically; you must build .exe, then sign the finished file with signtool using a certificate from hardware token or cloud HSM; no downloadable PFX since June 2023 — [Automate PyInstaller Builds and Code Signing on Windows](https://johanneskinzig.com/automating-pyinstaller-builds-and-code-signing-with-powershell.html)
- GitHub Actions workflow for Azure Trusted Signing requires .NET runtime, signtool, and environment variables set by Melatonin or similar helper action — [How to code sign Windows installers with an EV cert on GitHub Actions](https://melatonin.dev/blog/how-to-code-sign-windows-installers-with-an-ev-cert-on-github-actions/)

### Inferences
- Roadmap for Shizuoka-based team: if in Japan (non-US/Canada), EV certificates remain only option for Windows SmartScreen reputation; cost ~$200–400/year + $50–100/month DigiCert/Sectigo cert management. If moving US entity in future, switch to Azure Trusted Signing.
- unsigned .exe + local log of build hash is acceptable interim solution for internal lab use; SmartScreen warning is minor friction for academic team until reputation requirement becomes critical.
- CI/CD workflow: build .exe with PyInstaller, sign with signtool in GitHub Actions (requires Service Principal credentials in secrets), upload signed .exe to release.

### Gaps
- Japanese code signing certificate providers and pricing not researched
- DigiCert/Sectigo integration with GitHub Actions for Asia-based teams not detailed

---

## Auto-Update and Distribution: PyInstaller-Based Apps

### Takeaway
PyUpdater is archived and unmaintained; Tufup (inspired by PyUpdater, built on TUF) is the modern maintained replacement; Tufup is framework-agnostic, works with any packaging (PyInstaller, PEX, etc.) and uses TUF's cryptographic update verification.

### Cited Findings
- PyUpdater has been archived and is no longer maintained — [PyUpdater is no longer maintained · GitHub discussion](https://www.libhunt.com/posts/911739-pyupdater-is-no-longer-maintained-what-now-tufup-automated-updates-for-stand-alone-python-applications)
- Tufup was created as a replacement for archived PyUpdater, built on python-tuf (reference implementation of The Update Framework) — [tufup: Automated updates for stand-alone Python applications](https://github.com/dennisvang/tufup)
- Tufup advantage: framework-agnostic (unlike PyUpdater which is tightly integrated with PyInstaller); tufup simply moves bundles of files securely from server to client, regardless of how bundles were created — [tufup · GitHub](https://github.com/dennisvang/tufup)
- TUF (The Update Framework) provides cryptographic verification of update packages, protecting against rollback attacks, mix-and-match attacks, and expired metadata — [The Update Framework](https://theupdateframework.github.io/)

### Inferences
- For lab app: start with simple HTTP file-serving (Gist, GitHub Releases, institutional server) and tufup library; on app startup, check for version.json metadata, download .zip if newer available, verify signature with TUF metadata, unpack to temp, restart.
- Tufup example repository available; low implementation effort (~200 LOC for PyInstaller bundle).
- For privacy: Tufup supports air-gapped updates (download metadata/bundles to USB stick, install offline; no phone-home required).

### Gaps
- Velopack status and PyQt6 compatibility not researched (Velopack appears .NET-focused)
- Cost/effort to host auto-update server (S3, GitHub Releases, self-hosted) not compared

---

## Configuration Management: Persistence and Profiles

### Takeaway
QSettings is Qt's standard cross-platform persistence layer for application settings; PyQtConfig library simplifies widget synchronization; platformdirs provides OS-aware config directories; consider pydantic-settings for schema validation if moving toward TOML/YAML configs.

### Cited Findings
- QSettings provides cross-platform key-value persistence stored in registry (Windows), plist (macOS), INI files (Linux) without developer intervention — [PyQt6 QSettings Tutorial](https://www.pythonguis.com/faq/pyqt6-qsettings-how-to-use-qsettings/)
- QSettings can be configured with group prefixes, enabling hierarchical settings and automatic widget synchronization — [How to Use QSettings in PyQt6](https://www.pythonguis.com/faq/qsettings-usage/)
- PyQtConfig library provides ConfigManager and QSettingsManager to keep Qt widgets (QCheckBox, QLineEdit, QSpinBox, QRadioButton) in sync with a config dictionary and/or QSettings object — [PyQtConfig · GitHub](https://github.com/pythonguis/pyqtconfig)
- QStandardPaths class provides cross-platform access to application directories: ConfigLocation (user-specific), AppConfigLocation (app-specific, never empty), GenericConfigLocation (shared) — [QStandardPaths Class](https://doc.qt.io/qt-6/qstandardpaths.html)
- platformdirs.user_config_dir() provides portability across OSes (Windows, macOS, Linux) for choosing application config directories — [platformdirs · PyPI](https://pypi.org/project/platformdirs/)

### Inferences
- Recommended approach: use QSettings for GUI state (window size, last tab, checked boxes); use pydantic-settings + platformdirs for immutable config file (GPIB addresses, temperature ranges, thresholds) loaded once at startup. Store in ~/.config/TE_measurements/config.toml or Windows equivalent.
- Per-rig profile support: store settings files in per-rig subdirectory (e.g., ~/.config/TE_measurements/rigs/rig_shizuoka_01/config.toml); load via dropdown at app startup.
- Import/export config: serialize pydantic model to JSON for team sharing; button → File dialog → write config JSON to user-selected path.

### Gaps
- pydantic-settings integration patterns with PyQt6 not specifically documented in search results
- Multi-user (shared lab computer) profile switching without restart not researched

---

## Logging and Observability: Crash Reporting

### Takeaway
Structured logging with structlog + rotating file handler catches production issues; Sentry SDK for Python captures exceptions and sends to cloud dashboard; faulthandler dumps tracebacks on segfaults (rare in pure Python but important for C extension crashes).

### Cited Findings
- Structlog simplifies structured logging (JSON-formatted key-value pairs instead of plain text), enabling better log analysis and troubleshooting — [Leveling Up Your Python Logs with Structlog](https://www.dash0.com/guides/python-logging-with-structlog)
- RotatingFileHandler manages log files: set maxBytes (e.g., 10MB) and backupCount (e.g., 5 old files) to prevent disk space issues — [Python Logging Module: A Complete Guide](https://www.dash0.com/guides/logging-in-python)
- Sentry SDK for Python (sentry-python) integrates with applications to capture exceptions and send to Sentry service; official Python SDK actively maintained (last update Apr 2026) — [Sentry GitHub](https://github.com/getsentry)
- faulthandler module dumps Python tracebacks on crash (SIGSEGV, SIGFPE, SIGABRT, etc.); implemented in C so can dump traces when Python is deadlocked — [faulthandler — Dump the Python traceback](https://docs.python.org/3/library/faulthandler.html)
- Structlog can transform exceptions and render them in console-friendly format for debugging during development — [Complete Guide to Logging with StructLog in Python](https://signoz.io/guides/structlog/)

### Inferences
- For lab app: minimal setup is RotatingFileHandler writing to ~/.config/TE_measurements/logs/app.log with structlog JSON formatting. On startup, enable faulthandler with same log file.
- Optional (adds observability): Sentry free tier captures ~5,000 errors/month; useful for remote monitoring if app deployed to campus cluster. Environment variable SENTRY_DSN can be set at install time.
- Never log GPIB commands/raw data to avoid huge log files; log only state transitions (measurement started, heater on, error occurred) and aggregated stats (data points/sec, avg ΔT).

### Gaps
- Privacy considerations for Sentry on lab machine (data does leave localhost; check institutional data policies)
- Best practices for log retention (e.g., auto-purge logs >30 days old) not detailed

---

## Documentation and User Guidance

### Takeaway
MkDocs or Sphinx for user manual + API docs; in-app Help menu with tooltips on all controls; printed SOP cards at instrument; no substitute for on-the-spot training from senior grad students.

### Cited Findings
- MkDocs is lightweight static site generator for documentation, integrates with Material for Docs theme for professional appearance — [MkDocs](https://www.mkdocs.org/)
- Sphinx is standard for Python project documentation and can generate PDF manuals — [Sphinx](https://www.sphinx-doc.org/)
- Qt supports context-sensitive help via QWhatsThis and tooltips; keyboard shortcut F1 can trigger help on selected widget — [Qt Documentation](https://doc.qt.io/)

### Inferences
- Minimum documentation: (1) two-page Quick Start PDF (install, connect Keithley, run first measurement); (2) Wiki page for troubleshooting (common GPIB errors, temperature sensor not responding); (3) in-app tooltips on every control (describe units, typical ranges).
- SOP video: 5-min screen recording of typical I-V measurement workflow; post on lab intranet or YouTube.

### Gaps
- No guidance on multi-language documentation (Japanese + English)

---

## User Experience Patterns for Instrument Software

### Takeaway
Scientific instrument software UX is nascent field; Berkeley Lab's STRUDEL project has published a design system; key patterns: visible state machine (Idle/Ready/Running/Cooling/Error), non-modal notifications, pre-flight checklists, persistent status bar per instrument, emergency-stop placement.

### Cited Findings
- Berkeley Lab's STRUDEL project (Scientific sofTware Research for User experience, Design, Engagement and Learning) has developed design and planning framework for scientific software, addressing usability and accessibility gaps — [Berkeley Lab's STRUDEL Project](https://crd.lbl.gov/news-and-publications/news/2024/berkeley-labs-strudel-project-brings-uxui-methods-to-scientific-software-design/)
- UX-focused development at Oak Ridge National Laboratory (SNS, HFIR facility control system upgrades) demonstrates that UX is tool for higher scientific productivity — [UX Focused Development Work During Recent ORNL EPICS-Based Instrument Control](https://www.osti.gov/biblio/1873844)
- Laboratory instrument UX requires user-centered design principles: ergonomic considerations to enhance productivity, reduce cognitive load, interfaces tailored to high-stakes nature of lab work — [Creating Award-Winning UX for Lab Science](https://www.loft.design/insights/developing-the-right-ux-for-laboratory-science---panel-discussion)
- AI copilots expected to be built into lab management software and instrument control interfaces by 2025 — [The Ins and Outs of Lab Automation in 2025](https://blog.ganymede.bio/the-ins-and-outs-of-lab-automation-in-2025/)

### Inferences
- Implement visible state machine: display current state (Idle, Heating, Running, Cooling, Error) as prominent label or icon in top-right corner; use colour (green = Idle, yellow = Heating, red = Error) + text.
- Pre-flight checklist: before user clicks "Start Measurement", show modal dialog: "Heater warmed to 300K? [ ] GPIB connection OK? [ ] Liquid N2 level > 2L? [ ]"—checkboxes user must tick, or "Start" button stays disabled.
- Non-modal error notification: use persistent status bar at bottom instead of dismissible popup; show last 5 errors with timestamps in expandable panel.
- Unattended run notifications: if measurement queued for >1 hour, offer to send email notification when complete (optional feature, default off due to privacy).

### Gaps
- Specific design patterns for long-running experiments (>24h) not found
- Emergency-stop UX (hardware vs software interrupt) not researched

---

## Live Plotting at Scale: Performance and Responsiveness

### Takeaway
pyqtgraph's setDownsampling() method (peak/mean/subsample) is essential for live plots; maintain ring buffer (fixed-size circular buffer, 500–2000 points), window data to visible range; dvg-pyqtgraph-threadsafe library handles thread-safe buffering and auto-downsampling.

### Cited Findings
- dvg-pyqtgraph-threadsafe provides thread-safe plot curves (HistoryChartCurve, BufferedPlotCurve, PlotCurve) with underlying ring buffers for live data streaming — [dvg-pyqtgraph-threadsafe · GitHub](https://github.com/Dennis-van-Gils/python-dvg-pyqtgraph-threadsafe)
- PyQtGraph setDownsampling() offers three strategies: 'peak' (saw-wave following min/max, best fidelity but slower), 'mean' (averages N samples, faster), 'subsample' (every Nth sample, fastest but lossy) — [PlotDataItem documentation](https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/plotdataitem.html)
- Ring buffer (circular buffer) approach maintains fixed-size buffer, limits memory and rendering complexity; windowing data to visible range (500–2000 points) ensures consistent performance — [Real-Time Plotting in Python: PyQtGraph 2026 Complete Guide](https://copyprogramming.com/howto/what-is-the-easiest-way-to-achieve-realtime-plotting-in-pyqtgraph)
- autoDownsample flag in pyqtgraph plots automatically adjusts downsampling based on visible range, maintaining responsiveness as user zooms/pans — [PlotDataItem documentation](https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/plotdataitem.html)

### Inferences
- Current app re-plots full arrays every second: switch to dvg-pyqtgraph-threadsafe for thread-safe ring buffer. Append new (T, R, dT) point each second, trim to last 1000 points, redraw only visible portion.
- For long runs (>1 hour), downsample to 'mean' with bin size 10–50 to avoid re-plotting 3600+ points/hour at high frequency.
- High-DPI handling: pyqtgraph auto-scales for DPI; set devicePixelRatio on QApplication startup (Qt6 does this automatically).

### Gaps
- Specific numbers for TE measurement: how many data points/sec captured from Keithley; how many curves on screen simultaneously
- Memory profiling of long-run ring buffers (1M+ points) not researched

---

## Dark Mode and Theming

### Takeaway
PyQtDarkTheme (qdarktheme) is mature, mature, actively maintained library for PyQt6; syncs with OS theme (Windows, macOS, Linux), offers customizable accent colors and corner styles; Qt-Material offers Material Design aesthetic alternative.

### Cited Findings
- PyQtDarkTheme applies flat dark theme to QtWidgets applications, supports PySide6, PyQt6, PyQt5, PySide2; syncs with OS's theme and accent color — [PyQtDarkTheme documentation](https://pyqtdarktheme.readthedocs.io/en/stable/how_to_use.html)
- qdarktheme.setup_theme("auto") syncs with operating system theme preference (light/dark) and respects macOS accent colors — [PyQtDarkTheme: How to use](https://pyqtdarktheme.readthedocs.io/en/stable/how_to_use.html)
- qdarktheme library overrides QStyle.standardIcon() to provide Google Material Design Icons that automatically adjust colors when themes change — [PyQtDarkTheme documentation](https://pyqtdarktheme.readthedocs.io/en/stable/how_to_use.html)
- PyQtDarkTheme supports customization: custom_colors parameter adjusts specific colours (e.g., primary accent), corner_shape parameter changes border appearance ("sharp" vs "rounded") — [PyQtDarkTheme documentation](https://pyqtdarktheme.readthedocs.io/en/stable/how_to_use.html)
- Qt-Material is modern stylesheet library for PySide6 and PyQt6 inspired by Material Design, offers dark/light themes, custom accent colors, runtime theme switching, density scaling for accessibility — [Qt-Material documentation](https://qt-material.readthedocs.io/en/latest/index.html)

### Inferences
- Minimal implementation: add two lines at app startup after QApplication creation:
  ```python
  import qdarktheme
  qdarktheme.setup_theme("auto")
  ```
- Users can override in Settings menu to force light/dark regardless of OS preference.
- Custom accent color for "Ready" / "Running" / "Error" states: use custom_colors to set primary accent to green/yellow/red during measurement.

### Gaps
- Integration with existing hardcoded colours in current app not researched
- Per-curve colour customization for multiple simultaneous plots not found

---

## Accessibility: Keyboard Navigation, Colour-Blind Safe Palettes

### Takeaway
WCAG 2.1.1 Keyboard Accessibility requires Tab/Shift+Tab/Arrow/Enter/Space navigation; Okabe-Ito palette provides 8 hues safe for all colour vision deficiencies; focus indicator must have ≥3:1 contrast ratio, minimum 2px width.

### Cited Findings
- WCAG 2.1.1 "Keyboard Accessible" standard requires all functionalities operable via Tab, Shift+Tab, Enter, Space, Arrow keys, Escape — [WCAG 2.1.1 Keyboard Accessibility](https://www.uxpin.com/studio/blog/wcag-211-keyboard-accessibility-explained/)
- Focus indicators require ≥3:1 contrast ratio against adjacent colors; use visible outline (minimum 2px width) and apply consistent focus styles across all interactive elements — [How to Implement Keyboard Navigation Accessibility](https://www.accessibilitychecker.org/blog/keyboard-navigation-accessibility/)
- Okabe-Ito palette provides 8 hues distinct across common colour vision deficiencies (protanopia, deuteranopia, tritanopia); most widely cited colorblind-safe palette in scientific data visualization communities — [A Guide to Colour Blind Friendly Colours in Design](https://wearearch.com/blog/color-blind-friendly-colours)
- Blue and orange pairing is safest everyday colour combination, as red-green deficiency leaves blue perception largely intact — [Colorblind-Friendly Palettes for Web Design](https://www.audioeye.com/post/colorblind-friendly-palettes/)

### Inferences
- Audit current app: Tab through all controls (GPIB address input, Start button, temperature setpoint, chart), ensure logical order (left-to-right, top-to-bottom).
- Replace colour-only status cues: "Ready" should be green + label "Ready" (not green square alone); "Error" should be red + label "Error".
- For plot curves (resistance vs temperature, etc.): use subset of Okabe-Ito palette instead of [blue, green, red, purple, ...]; example: black, orange, sky-blue, green, red.
- Qt accessibility: QWidget.setAccessibleName(), setAccessibleDescription() for screen readers; Qt automatically handles keyboard navigation if controls are in QLayout with tab order set.

### Gaps
- Testing colour-blind-safe palettes on actual monitors (not just hex values) not covered
- Screen reader testing for PyQt6 (NVDA on Windows) not researched

---

## Internationalization (i18n): Japanese + English UI

### Takeaway
Qt Linguist toolchain (lupdate, lrelease, QTranslator) is standard for PyQt6 i18n; workflow: wrap UI strings in tr("..."), run lupdate to extract to .ts files, translate with Qt Linguist GUI, run lrelease to compile .qm files, load via QTranslator at startup.

### Cited Findings
- Qt Linguist, lupdate, lrelease are translation tools installed in Qt bin directory; Qt Linguist GUI is self-explanatory — [Internationalization with Qt](https://doc.qt.io/qt-6/internationalization.html)
- QTranslator provides internationalization support for text output and functions to look up translations in .qm files — [QTranslator Class](https://doc.qt.io/qt-6/qtranslator.html)
- To make application usable by Japanese users requires not only different languages but different input techniques, character encodings, and presentation conventions; Asian languages written without word spaces require special line-breaking support — [Internationalization with Qt](https://doc.qt.io/qt-6/internationalization.html)
- Typical i18n workflow: wrap UI strings with tr("..."), run lupdate tool to extract strings to .ts XML files, translate using Qt Linguist editor, run lrelease to generate compiled .qm binary files — [Writing Source Code for Translation](https://doc.qt.io/qt-6/i18n-source-translation.html)

### Inferences
- Minimal i18n for lab app: extract all UI strings (button labels, menu items, error messages) to tr("...") calls. Use PyQt6 Linguist tools to support English and Japanese.
- For PyQt6 code, wrap Python strings: `self.label.setText(tr("Measurement in progress"))` (tr imported from PyQt6.QtCore).
- Defer dynamic strings (GPIB error codes from instrument) to separate .qm file for each language or use translation API.
- Line breaks: Japanese text flows differently; test UI layout with full-width characters and longer phrases (e.g., "測定中" 3 chars vs "Measurement in progress" 25 chars in English).

### Gaps
- Best practices for translating scientific terminology (TE, resistivity, carrier concentration) not researched
- Tool support for managing Japanese character encoding in .ts files not detailed

---

## ISO 9241 and IEC 62366: Usability Standards for Laboratory Instruments

### Takeaway
ISO 9241 series (parts 11, 110, 210) defines usability heuristics, measurement, and human-centered design for ergonomic office software; IEC 62366-1 applies these to medical device UX with focus on safety; both emphasize iterative user testing and risk reduction.

### Cited Findings
- ISO 9241 is international series of ergonomics requirements for office work with visual display terminals; parts 11–19 address software usability, with Part 110 providing general usability heuristics and Part 11 addressing measurement of usability — [ISO 9241](https://en.wikipedia.org/wiki/ISO_9241)
- ISO 9241-11:2018 defines usability as "The extent to which a product can be used by specified users to achieve specified goals with effectiveness, efficiency and satisfaction in a specified context of use" — [ISO 9241 & IEC 62366](https://usability-academy.com/en/articles-all/400-iso-9241-iec-62366-many-norms-pardon)
- IEC 62366-1:2015 specifies usability engineering for medical devices with focus on safety-related aspects; adopts human-centered design principles from ISO 9241-210 — [IEC 62366](https://en.wikipedia.org/wiki/IEC_62366)
- IEC 62366 requires usability evaluation with representative users, hazard and risk analysis tied to UX, and verification that design mitigates identified risks — [IEC 62366 in medical software](https://revolve.healthcare/blog/iec62366-medical-software)

### Inferences
- For academic thermoelectric lab app: ISO 9241 is more applicable than IEC 62366 (no medical safety concerns); conduct informal usability testing with grad students and postdocs (representative users).
- Apply ISO 9241-110 heuristics: provide clear feedback (state machine visible), minimize memory load (remember last settings), enable user control (cancel long-running measurements), consistency across UI.
- Risk analysis: identify high-stakes actions (heater on, liquid N2 flow start); require confirmation or mode-based disabling to prevent accidental triggers.

### Gaps
- Specific ISO 9241 checklist for scientific instrument UX not available
- Compliance testing procedures and costs not researched

---

## Publishing and Credibility: JOSS Paper and Zenodo DOI

### Takeaway
Journal of Open Source Software (JOSS) publishes peer-reviewed papers on research software (>2400 papers published since 2016); submitting to JOSS involves archiving code on Zenodo or Figshare and linking DOI in paper; provides academic citation credit and credibility for lab software.

### Cited Findings
- JOSS was created in 2016 to publish peer-reviewed papers about research software themselves; >2400 papers published across scientific domains — [Publish your software! A walkthrough of JOSS submission to publication](https://zenodo.org/records/14290378)
- JOSS publication process: complete peer review on GitHub, then author archives software on Zenodo/Figshare (generating DOI), adds DOI to paper, and JOSS publishes final paper with DOI link — [The Journal of Open Source Software](https://zenodo.org/records/13942443)
- JOSS introduced "substantial scholarly effort" criterion to ensure only meaningful contributions are published; benchmark ~3 months of developer time — [The Journal of Open Source Software (JOSS): An open community and platform](https://zenodo.org/records/18849550)
- JOSS provides developers venue to publish complete research software wrapped in high-level articles, enabling citation credit for work and promoting transparency, reproducibility, collaboration — [PeerJ Journal of Open Source Software (JOSS): design and first-year review](https://peerj.com/articles/cs-147/)

### Inferences
- Once TE measurement app reaches ~1000+ lines, stable API, and documentation, consider JOSS submission (typically 6–12 month lead time for review and publication).
- JOSS paper template: ~500 words describing software purpose, key features, scientific domain, and research impact. Example: "Thermoelectric property measurement and analysis software for high-throughput materials screening."
- Zenodo archival: create GitHub release, upload to Zenodo (integrates with GitHub), get DOI, cite in JOSS paper.
- Citation credit: JOSS paper becomes academic publication; lab members list on CV as co-authors; improves credibility for grant proposals.

### Gaps
- JOSS review timeline and rejection rate not found
- Cost/effort for data curation to meet JOSS archival standards not researched

---

## Summary: Recommended Implementation Roadmap for 1–3 Person Team

### Phase 1 (Immediate, 2–4 weeks)
- [ ] Add pytest-qt + headless GUI tests to CI
- [ ] Configure Ruff + Pyright in pyproject.toml, run locally before commit
- [ ] Implement QSettings for window state persistence; add pydantic-settings for GPIB config
- [ ] Add dark mode with PyQtDarkTheme (2 lines of code)
- [ ] Audit keyboard navigation (Tab order), add Okabe-Ito palette to plots

### Phase 2 (Short-term, 1–3 months)
- [ ] Set up GitHub Actions CI to build PyInstaller .exe, run pytest-qt headless
- [ ] Implement structlog + rotating file handler for crash logging
- [ ] Add pre-flight checklist modal before measurement start
- [ ] Wrap UI strings with tr() for Qt Linguist i18n pipeline
- [ ] Document Quick Start SOP in MkDocs

### Phase 3 (Medium-term, 3–6 months)
- [ ] Implement tufup auto-update mechanism (optional; internal lab deployment may not need)
- [ ] Deploy Sentry for exception tracking if running on campus servers
- [ ] Conduct informal usability testing with grad students; iterate on UX
- [ ] Add tooltips and "What's This?" help to all controls
- [ ] Consider Azure Trusted Signing for production .exe distribution (if outside US/Canada, defer to later)

### Phase 4 (Long-term, 6–12 months, optional for academic sustainability)
- [ ] Publish JOSS paper + archive on Zenodo
- [ ] Implement run queue and remote monitoring (email/Slack notifications)
- [ ] Add Japanese translation and test with Japanese-fluent lab member
- [ ] Contribute instrument simulation profiles to pyvisa-sim for community benefit

---

## Tool Costs and Vendor Status (2025–2026)

| Tool | Cost | Status | Notes |
|------|------|--------|-------|
| pytest-qt | Free/OSS | Actively maintained (v4.5.0, Jul 2025) | PyPI, widely used |
| PyQtDarkTheme | Free/OSS | Actively maintained | Material Design theme alternative available |
| Pyright | Free/OSS | Actively maintained by Microsoft | Faster than mypy, powers VS Code Pylance |
| Ruff | Free/OSS | Actively maintained | Replaces flake8, Black, isort; Rust-based, very fast |
| Tufup | Free/OSS | Maintained (replaces PyUpdater) | Built on TUF standard, cryptographically secure |
| Azure Trusted Signing | $9.99/month | Available (restricted to US/Canada/EU/UK, 3+ year business history as of Apr 2026) | Modern alternative to EV certificates |
| Sentry (free tier) | Free | Actively maintained | ~5000 errors/month, good for small teams |
| Qt Linguist | Included with Qt | Native Qt tool | Part of any Qt installation |
| MkDocs | Free/OSS | Actively maintained | Material theme available |
| GitHub Actions | Free tier included | Available | 2000 min/month free, Windows runners ~10 min/build |

---

## References and Further Reading

### Official Documentation
- [pytest-qt](https://pytest-qt.readthedocs.io/)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [Qt 6 Documentation](https://doc.qt.io/qt-6/)
- [PyInstaller Manual](https://pyinstaller.org/)
- [Sentry Python SDK](https://docs.sentry.io/platforms/python/)
- [Tufup Documentation](https://github.com/dennisvang/tufup)

### Research Projects
- [Berkeley Lab STRUDEL Project](https://crd.lbl.gov/news-and-publications/news/2024/berkeley-labs-strudel-project-brings-uxui-methods-to-scientific-software-design/)
- [Oak Ridge EPICS Instrument Control UX](https://www.osti.gov/biblio/1873844)

### Standards
- [ISO 9241 (Wikipedia)](https://en.wikipedia.org/wiki/ISO_9241)
- [IEC 62366 (Wikipedia)](https://en.wikipedia.org/wiki/IEC_62366)
- [WCAG 2.1 Keyboard Accessibility](https://www.uxpin.com/studio/blog/wcag-211-keyboard-accessibility-explained/)

### Community
- [US-RSE (US Research Software Engineering)](https://us-rse.org/)
- [Better Scientific Software (bssw.io)](https://bssw.io/)
- [Journal of Open Source Software (JOSS)](https://joss.theoj.org/)

