# Build Industry-Standard Thermoelectric Measurement Software Now

A PyQt6 Windows desktop application can evolve into an industry-standard, ISO 17025–benchmarked scientific instrument-control platform by integrating three converging layers: (1) **standards-driven data management and safety engineering** (IEC 61010, IEC 61508, GAMP 5, measurement uncertainty per JCGM 100, FAIR data principles), (2) **open-source lab-automation architecture patterns** from mature frameworks (PyMeasure, QCoDeS) that decouple measurement logic from hardware specifics, and (3) **enterprise-grade software engineering practices** (automated testing, type checking, configuration management, audit trails). The current gaps documented in the SOFTWARE_REVIEW.md (critical SAF-1 / SAF-2 over-temperature control, data-integrity issues DATA-1 through DATA-4, configuration brittleness CFG-1 through CFG-4) map directly to industry standards and commercial system capabilities; fixing them requires 3–6 months of focused effort across safety hardware, database migration, and measurement architecture refactoring. Prioritize layered safety (Phase 1: software limits and sensor validation; Phase 2: independent hardware interlocks), YAML-based configuration, SQLite with Alembic migrations, and HDF5/NeXus data export as the minimal-viable-product for reproducibility and world-class quality. ISO 17025 accreditation is an optional future step that becomes feasible once this foundation is in place.

## Standards, Regulations, and Accreditation Pathways Converge on Software Validation

**ISO/IEC 17025:2017 Clause 7.11 mandates software validation for all laboratory systems**. For custom instrument-control software like the TE measurement app, this means **requirements specification, design documentation, unit/integration/system testing, and traceability matrices are mandatory audit deliverables**, not optional. The 2025 edition (published Sept 27, 2025, three-year transition through Sept 30, 2028) is reported to extend these requirements to digital data management and electronic audit trails; verify the specific scope and transition timeline with JAB or the International Accreditation Forum ([ISO/IEC 17025:2017 Guidance](https://17025store.com/iso-iec-17025-2017-requirements/clause-7-process-requirements/)). The framework adopted matters: GAMP 5 classifies wholly custom, bespoke software (Category 5) as requiring the most rigorous validation—documented code review, full test coverage, V&V protocols—with proportionate effort for simpler categories; this rigor reflects the principle that measurement software is only as trustworthy as its validation evidence ([GAMP 5 Guidelines](https://intuitionlabs.ai/pdfs/gamp-5-computerized-system-validation-in-pharma.pdf)). International accreditation bodies (JAB for Japan, A2LA for US, UKAS for UK) all reference ISO 17025 as the baseline standard; none offer reduced compliance for academic labs. **Immediate action**: adopt SQLAlchemy with Alembic for versioned schema migrations (replacing the current `create_all()` pattern that cannot be deployed to existing lab installations); implement ALCOA+ principles with append-only audit logs capturing user, action, timestamp, and rationale for key events (run start/stop/abort, settings changes, reprocessing, geometry updates, exports); deploy pytest-qt headless testing in CI/CD to validate GUI and physics calculations without hardware.

IEC 61010-1 and IEC 61010-2-010 together establish that **laboratory heating equipment must have automatic over-temperature shutoff and fail-safe design** ([IEC 61010-1:2010](https://standards.globalspec.com/std/13250090/iec-61010-1) and [IEC 61010-2-010:2020](https://knowledge.bsigroup.com/products/safety-requirements-for-electrical-equipment-for-measurement-control-and-laboratory-use-particular-requirements-for-laboratory-equipment-for-the-heating-of-materials)). The current app has **none** (SAF-1, SAF-2): no over-temperature cutoff, no independent heater shutdown, no watchdog timer. IEC 61508 defines Safety Integrity Levels (SILs); a general-purpose PC application should not be the sole safety layer, and software alone cannot be certified as the only protection mechanism ([IEC 61508 and SILs](https://en.wikipedia.org/wiki/IEC_61508)). **Layered protection is essential**, combining software limits with independent hardware shutdown. Software can monitor and set limits, but cannot survive its own crash or a PC kernel hang. The protective layers needed are: (1) **software limits** (T_max and dT/dt checks in code, per-rig configuration); (2) **instrument-level protections** (Keithley 2700 open-thermocouple detection, Matsusada P4K-80M current limit ICN); (3) **independent hardware limit controller** with its own thermocouple sensor (not relying on the Keithley 2700 or PC software), driving a contactor to cut the P4K-80M's input AC power or DC output; (4) **DC-rated thermal fuse** on the heater fixture as the ultimate fallback. This follows the intent of IEC 61010-2-010 and functional-safety practice. **Many university EHS policies restrict unattended heating without independent fail-safe controls**; the lab should confirm Shizuoka University's policy with the safety office. The TE lab cannot run unattended experiments until Phase 2 hardware (limit controller + contactor + thermal fuse) is installed, tested, and verified to operate independently of the PC and software.

JCGM 100:2008 (the GUM—Guide to the Expression of Uncertainty in Measurement) is the universal framework for quantifying measurement uncertainty ([JCGM 100:2008](https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf)). Thermoelectric measurements have large systematic uncertainties dominated by **cold-finger effect, thermal contact resistance, and probe-spacing errors** (up to ±13% at high temperature in peer-reviewed interlaboratory studies) ([Alleno et al. Round-Robin](https://pubs.aip.org/aip/rsi/article-abstract/86/1/011301/360853) and [Cold-Finger Effect Analysis](https://ui.adsabs.harvard.edu/abs/2021MeScT..32c5014E/abstract)). NIST SRM 3451 provides a certified Seebeck reference standard (n-type Bi₂Te₃, 10–390 K) used internationally for calibration ([NIST SRM 3451](https://tsapps.nist.gov/srmext/certificates/3451.pdf)). **Accreditation requires demonstrating traceability via SRM verification and documenting measurement uncertainty budgets** with explicit cold-finger, thermal contact, and probe-spacing components. The current app (DATA-3, CALC-1) stores no uncertainty flags, silent correction fallbacks, and lacks re-processing capability to apply corrected parameters post-hoc (Quantum Design PPMS provides this via reprocess commands).

For Japan-specific compliance, **JAB (Japan Accreditation Board) and JCSS (Japan Calibration Service System) mirror ISO/IEC 17025** and recognize ILAC mutual-recognition agreements ([JAB Overview](https://www.jab.or.jp/en/system/service/calibrationlaboratories/accreditation/detail/138/)). No Japan-specific laxity exists. **ARIM-mdx (Advanced Research Infrastructure for Materials)**, operated by NIMS for Japanese universities, provides cloud storage and direct data transfer infrastructure; alignment with NOMAD Metainfo schemas and ARIM metadata standards facilitates data sharing and funding-agency compliance ([ARIM-mdx System](https://arxiv.org/abs/2409.06734)).

## Commercial Thermoelectric Systems Converge on Proven Patterns; University Software Can Adopt Them

Linseis LSR, ULVAC ZEM-3 (worldwide de facto standard), and Quantum Design PPMS TTO all share convergent software workflows: **pre-measurement V-I (ohmic contact) validation, simultaneous Seebeck + resistivity measurement, automated temperature-stepped sequences, Windows-based control, and CSV/binary export** ([Linseis LSR Brochure](https://www.linseis.com/wp-content/uploads/2024/07/Linseis-LSR-Seebeck-and-Electric-Resistivity-Analyzer-v7.pdf), [ULVAC ZEM-3 SOP](https://subramanian.chem.oregonstate.edu/sites/subramanian.chem.oregonstate.edu/files/ULVAC%20ZEM-3%20SOP.pdf), and [PPMS MultiVu Manual](http://mrlweb.mrl.ucsb.edu/sites/default/files/mrl_docs/instruments/multiPPMS.pdf)). **Measurement uncertainties are standard**: ±7% (Seebeck), ±10% (electrical conductivity), ±3% (thermal diffusivity), with combined ZT uncertainty ≈15–20% ([Measurement Uncertainties in TE Research](https://www.researchgate.net/publication/291295184_Measurement_uncertainties_in_thermoelectric_research)). **V-I curve validation is mandatory** across all commercial systems as a pre-measurement quality gate—it detects contact problems before costly sample time is wasted ([ZEM-3 SOP and Netzsch SBA 458 Brochure](https://analyzing-testing.netzsch.com/_Resources/Persistent/0/a/0/5/0a050e36701950d3074970981be18c5870b79324/SBA_458_Nemesis_en_web.pdf)). 

The current TE app does **none of this systematically**: no V-I pre-check, no simultaneous dual-parameter collection (separate Seebeck/I-V runs), no error propagation to Seebeck coefficient, no reprocessing workflow. Commercial systems' **lack of documented remote monitoring, unattended operation, or role-based access control** represents a market gap—the Shizuoka lab can differentiate by adding these. **Configuration wizards, automatic sample-carrier recognition, and preset measurement templates** reduce operator error and training time; the current app's hardcoded GPIB addresses (CFG-1) and settings that don't persist (CFG-1) are 10+ years behind commercial practice.

Calibration in commercial systems is **outsourced to factory service or manual verification with NIST standards**; no published user-accessible calibration workflows exist ([Advance Riko ZEM-3L simulation](https://advance-riko.com/en/products/zem-3/) and independent NASA ZEM-3 LabVIEW implementation suggest commercial software underserves uncertainty tracking). **The university system should implement user-level calibration hooks**: capture data from SRM 3451 measurements, compute systematic offsets, store calibration constants in configuration, and apply them post-hoc during data reprocessing.

## Open-Source Lab-Automation Frameworks Provide Proven Architecture Patterns; PyMeasure and QCoDeS Are Production-Ready

**PyMeasure** (MIT license, 779 GitHub stars, active) provides **Keithley 2182A, Keithley 2700, and Keithley 2400-series drivers** (verify Keithley 2401 compatibility), a clean Procedure/Experiment/Results/Worker architecture, and FakeInstrument testing utilities ([PyMeasure Keithley Drivers](https://pymeasure.readthedocs.io/en/latest/api/instruments/keithley/) and [PyMeasure Architecture](https://www.simplico.net/2025/07/19/how-to-use-pymeasure-for-automated-instrument-control-and-lab-experiments/)). **No PyMeasure driver exists for the Matsusada P4K-80M heater supply; a custom hardware abstraction layer class is required** to communicate with it via GPIB. **QCoDeS** (maintained by Microsoft, version 0.59–0.61 as of 2025) adds **YAML-based Station configuration, SQLite dataset storage with metadata snapshots, and pyvisa-sim integration for hardware-free testing** ([QCoDeS Station](http://microsoft.github.io/Qcodes/examples/basic_examples/Station.html) and [QCoDeS Dataset](http://microsoft.github.io/Qcodes/dataset/dataset_design.html)). **Bluesky** (synchrotron community, NSLS-II, deployed at scale) provides **RunEngine orchestration and Ophyd device abstraction but is architecturally heavyweight for a 3-person lab with 5 instruments**; reserve Bluesky for future expansion to multi-measurement-type systems.

**Key pattern all frameworks adopt: Hardware Abstraction Layer (HAL).** Each instrument (Keithley 2182A, 2700, 2401, Matsusada P4K-80M, Optris camera) becomes a Python class with uniform interface—`read()`, `write()`, `configure()`, `get_status()`—decoupling measurement logic from device specifics. This enables **testing measurement procedures with simulated instruments** (pyvisa-sim YAML files) without hardware, critical for CI/CD pipelines ([pyvisa-sim Blog](http://python-in-the-lab.blogspot.com/2015/02/pyvisa-sim-test-your-pyvisa.html)). Current app mixes concerns: ~300-line worker function (SAF-4, UI-1) interleaves GPIB communication, maths, database writes, and UI updates on a single thread—refactoring into Procedure classes (one per measurement type) and HAL classes (one per device) is essential.

**Threading model matters.** PyQt6's QThread Worker pattern (not subclassing QThread) is correct; move Worker to QThread via `.moveToThread()`, ensure thread-safe signal/slots via queued connections, and protect shared data with QMutex ([RealPython QThread](https://realpython.com/python-pyqt-qthread/)). Modern alternative: **qasync / asyncio** eliminates thread-affinity hazards, but requires broader refactor. Immediate fix: migrate from QTimer-polled threading.Thread to formal Worker pattern with one QMutex per instrument/GPIB bus.

**Configuration management pattern: YAML + pydantic.** QCoDeS Station loads all instrument addresses, parameter limits, and aliases from a single `.yaml` file ([QCoDeS Station](http://microsoft.github.io/Qcodes/examples/basic_examples/Station.html)). Replace hardcoded `ADDR_2700 = 16` with `config.yaml` loaded at startup via pydantic validation. Same YAML can point to real GPIB instruments or pyvisa-sim for testing; switch via environment variable. This solves CFG-1 (settings don't persist) and enables multi-rig setups (separate config files per lab).

## Data Management, Reproducibility, and Audit Trails Are Now Regulatory Requirements; HDF5/NeXus + SQLite + ALCOA+ Enable Compliance

**FAIR Data Principles** (Findable, Accessible, Interoperable, Reusable) have become important drivers in funding-agency data stewardship policies; funding agencies and journals increasingly request FAIR-compliant data sharing ([FAIR Guiding Principles](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4792175/) and [ARIM-mdx / MaRDA Working Groups](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=959149)). **HDF5 with NeXus application definitions** is the globally standardized format for scientific measurement data ([HDF5 and NeXus](https://dawnsci.org/hdf5/)) with advantages over Zarr or netCDF4 for single-writer local workflows. **Raw data must be immutable and separate from derived quantities** (DATA-3, CALC-1 silent fallbacks): store raw T1, T2, ΔT, V, I as numeric columns in SQLite or HDF5 datasets, compute Seebeck on-demand with provenance records (which raw fields, which algorithm, parameter values). Reprocessing with corrected calibration or geometry should regenerate results without modifying raw data ([Bluesky Event Model](https://blueskyproject.io/event-model/main/explanations/data-model.html) and [RO-Crate Provenance](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0309210)).

**ALCOA+ principles** (Attributable, Legible, Contemporaneous, Original, Accurate, Complete, Consistent, Enduring, Available, Traceable) are now industry best-practice for data integrity ([ALCOA+ Principles](https://totallab.com/resources/alcoa-principles/)). Implement via: (1) **append-only audit log table** capturing user, timestamp, action (run start/stop/abort, settings changes, reprocessing, geometry updates, exports, user/role changes)—never overwrite, only insert new records; (2) **SQLite Write-Ahead Logging (WAL)** for crash durability ([Write-Ahead Logging](https://en.wikipedia.org/wiki/Write-ahead_logging)); (3) **per-run SHA-256 hash** of raw data block, validated on re-open to detect corruption; (4) **run state enum** (running/paused/crashed/completed) with cleanup on startup to mark orphaned runs (DATA-3 leaves them stuck "running" forever). Current practice (JSON blob per row, SHA-256 only for I-V) is insufficient.

**Electronic lab notebook integration** (eLabFTW, Kadi4Mat) should be **asynchronous and optional**: after run completes, user clicks "Archive to ELN" button that POSTs metadata + HDF5 reference to REST API without blocking workflow ([eLabFTW REST API v2](https://doc.elabftw.net/api/elabapi-html/) and [Kadi4Mat Integration](https://www.mdpi.com/1465596)). For Shizuoka, **ARIM-mdx may be the institutional recommendation**; check with NIMS Data Integration Center for metadata schema alignment.

**Database schema evolution via Alembic** is mandatory for fielded software ([Alembic de facto standard](https://oneuptime.com/blog/post/2025-07-02-python-alembic-migrations/view)). Replace `metadata.create_all()` with explicit migrations. At startup: (1) check if `alembic_version` table exists, (2) if not, initialize via `alembic upgrade head`, (3) if exists but behind, backup database file and run `alembic upgrade head`. Use Alembic's batch mode for SQLite to handle ALTER operations. This solves DATA-4 (no migrations); existing installations can export to CSV, create fresh schema, re-import, validate row counts.

## Software Engineering Quality and User Experience Follow Proven Scientific Software Patterns; Testing, Type Safety, and Accessibility Are Non-Negotiable

**Automated testing is essential for small teams.** pytest-qt with headless Qt (QT_QPA_PLATFORM=offscreen) enables CI/CD testing of GUI and measurement logic without physical display ([pytest-qt](https://pypi.org/project/pytest-qt/)). pyvisa-sim YAML-based simulated instruments enable testing all measurement procedures (I-V sweeps, temperature ramps) in CI without hardware—cheap and fast. Pair with pytest + pytest-cov to track test coverage; start at 60%, progressively increase to 80%+. **Type checking via Pyright** (Microsoft, powers VS Code Pylance) catches common bugs—wrong Numpy dtypes, None access, dict key mismatches—at zero runtime cost ([Pyright](https://pydevtools.com/handbook/reference/pyright/)). **Linting via Ruff** (Rust-based, vastly faster than flake8) enforces consistency ([Ruff 2025](https://osquant.com/papers/python-tooling-in-2025/)). All configured in `pyproject.toml`; no external CI tools needed initially.

**GitHub Actions CI/CD** can build PyInstaller .exe, run pytest-qt headless, and generate release artifacts within free tier (2000 min/month Windows runners). Use aqtinstall for headless Qt setup and cache it to avoid 10+ min downloads per build ([aqtinstall](https://aqtinstall.readthedocs.io/) and [Qt in GitHub Actions](https://medium.com/@bgallois/qt-series-s01e01-github-actions-qt-7be4c7fdad0f)).

**Configuration persistence via QSettings + pydantic-settings**: QSettings (Qt's cross-platform key-value store) handles GUI state; pydantic-settings validates immutable configuration files (GPIB addresses, parameter limits) loaded once at startup ([QSettings Tutorial](https://www.pythonguis.com/faq/pyqt6-qsettings-how-to-use-qsettings/) and [platformdirs](https://pypi.org/project/platformdirs/)).

**Logging and crash reporting**: structlog for structured JSON logs + rotating file handler; Sentry Python SDK optional for remote exception tracking if deployed on campus servers ([structlog](https://www.dash0.com/guides/python-logging-with-structlog) and [Sentry Python](https://github.com/getsentry)). Keep instrument I/O (GPIB commands/responses) at DEBUG logging level, disabled by default, enabled only for diagnosis; log state transitions (measurement start/stop, heater on/off, errors) at INFO level to avoid huge log bloat.

**User Experience for scientific instruments** is nascent but advancing. Berkeley Lab's STRUDEL project emphasizes **visible state machines (Idle/Ready/Running/Cooling/Error) with non-modal notifications, pre-flight checklists (checklist modal before start), and persistent per-instrument status indicators** ([STRUDEL Project](https://crd.lbl.gov/news-and-publications/news/2024/berkeley-labs-strudel-project-brings-uxui-methods-to-scientific-software-design/)). **ISO 9241 (ergonomics for software) and IEC 62366-1 (usability for medical devices) require iterative user testing with representative users** ([ISO 9241](https://en.wikipedia.org/wiki/ISO_9241) and [IEC 62366](https://en.wikipedia.org/wiki/IEC_62366)). For a 3-person lab, informal testing with grad students is sufficient; capture observations in a spreadsheet and iterate.

**Live plotting must be efficient:** pyqtgraph with downsampling (`setDownsampling()` peak/mean/subsample), ring-buffer data structures limiting to 500–2000 visible points, and `autoDownsample` flag ([dvg-pyqtgraph-threadsafe](https://github.com/Dennis-van-Gils/python-dvg-pyqtgraph-threadsafe)). Current app (UI-2) re-plots full history every second, causing slowdown on multi-hour runs.

**Dark mode via PyQtDarkTheme** is 2 lines of code and syncs with OS theme; Material Design themes available ([PyQtDarkTheme](https://pyqtdarktheme.readthedocs.io/en/stable/how_to_use.html)). **Accessibility**: Okabe-Ito colour palette is safe for all colour-vision deficiencies; use it for plot curves ([Colour Blind Friendly Palettes](https://wearearch.com/blog/color-blind-friendly-colours)). Tab/keyboard navigation must be audited; Qt accessibility works if controls are in QLayout with proper tab order.

**Internationalization via Qt Linguist**: wrap UI strings with `tr()`, run `lupdate` to extract to .ts files, translate with Qt Linguist GUI, run `lrelease` to generate .qm binaries, load via QTranslator at startup ([Qt i18n](https://doc.qt.io/qt-6/internationalization.html)). For Japanese + English, defer dynamic strings (GPIB error codes) to separate .qm files.

**Auto-update mechanism via Tufup** (successor to archived PyUpdater, built on TUF cryptographic verification) enables users to receive new versions without manual download ([Tufup](https://github.com/dennisvang/tufup)). For internal lab use, simple GitHub Releases + tufup is sufficient. **Code signing for Windows .exe** via Azure Trusted Signing ($9.99/month, instant SmartScreen reputation for US/Canada/EU/UK entities with 3+ year history) ([Azure Trusted Signing](https://melatonin.dev/blog/code-signing-on-windows-with-azure-trusted-signing/)); if outside this scope, unsigned .exe + local build-hash log is acceptable interim.

## Safety Engineering: Layered Protection Framework

The TE measurement rig implements heating via software-controlled Matsusada P4K-80M DC supply and temperature monitoring via Keithley 2700 thermocouples. **No single layer can be trusted to protect against all failure modes**; instead, five independent protective layers work in sequence:

1. **Software limits and plausibility checks** (Phase 1): T_MAX and dT/dt thresholds in configuration file, abort if exceeded; range/rate-of-change/stuck-value validation on every thermocouple read; GPIB timeout (3–5 s, tuned per instrument) to prevent indefinite hangs. **Protects against:** software logic errors, misconfigurations. **Does NOT protect against:** PC crash, kernel hang, OS deadlock, force-kill, power loss.

2. **Instrument-level protections** (existing, inherent): Keithley 2700 open-thermocouple detection (OTCD) alerts to failed sensors; Matsusada P4K-80M current-limit setting (ICN = 1.0–1.3 A) bounds output current. **Protects against:** sensor open-circuit, gross over-current. **Does NOT protect against:** runaway voltage (up to 80 V possible), sustained high-power dissipation, PC or GPIB failure.

3. **Independent hardware limit controller** (Phase 2): Standalone electronic controller with its own thermocouple sensor input (NOT the Keithley 2700), continuously monitoring temperature. On exceeding setpoint, drives a relay/contactor to de-energize the heater supply. **Protects against:** runaway heating, software crash, PC kernel hang, GPIB deadlock. **Does NOT protect against:** limit controller hardware failure, thermocouple sensor failure, mechanical failure of contactor. **Requirement:** limit controller must be **independent of the PC and software**—powered directly from AC/DC supply, not controlled by computer.

4. **DC-rated thermal fuse** (Phase 2): One-time passive fuse rated for the lab's maximum safe temperature (determined per rig, above max operating T_hot, below sample/fixture damage point). On reaching trip temperature, physically breaks the circuit. **Protects against:** limit-controller failure, contactor failure, software crash with limit-controller disabled. **Does NOT protect against:** fuse not installed, wrong rating, poor thermal coupling, fuse already blown from prior incident.

5. **Optional hardware watchdog timer** (Phase 4): USB-connected relay module that the PC must "heartbeat" every 5 seconds. If heartbeat stops (PC hang, crash, or kernel deadlock), relay cuts heater power. **Protects against:** OS-level kernel hang (the layer-3 limit controller still works, but watching from outside the OS provides additional redundancy). **Does NOT protect against:** watchdog hardware failure, watchdog not connected, watchdog power loss.

**In practice**, most heating-related incidents are caught by layers 1–3 (software limits, limit controller, thermal fuse). Layer 4 is optional and meant for extended unattended runs. **The critical point: layers 3 and 4 must remain active even if the PC crashes or is force-killed.**

## Prioritized Phased Roadmap: 3–6 Months to World-Class Quality

### Phase 1 (Immediate, 2–4 weeks): Software Safety & Data Integrity Foundation
**Goal:** Fix critical gaps preventing unattended operation; enable basic CI/CD.

**Safety (SAF-1, SAF-2, SAF-3, SAF-4):**
- [ ] Override PyQt6 `closeEvent()` with graceful shutdown: detect if a measurement is active; prompt user for confirmation; stop the session cleanly; wait for `output_off()` to complete before closing window.
- [ ] Add signal handlers (SIGINT, SIGTERM) and Windows console control event for forced termination; attempt clean shutdown but do not hang indefinitely.
- [ ] Register `atexit` cleanup function to run during normal Python exit; **note: `atexit` does NOT run on hard PC crashes, force-kill via Task Manager, or power loss—this is why hardware layer is essential**. For best effort, also hook SIGINT/SIGTERM.
- [ ] **Implement hardcoded software temperature limits** (per-rig configuration file): `T_MAX` = absolute maximum safe temperature (must be set above maximum planned operating T_hot and below sample/fixture damage point, determined by the lab), and `MAX_DTEMP_DT` = maximum safe rate of rise (°C/s); abort measurement if either is exceeded. Log to file if abort triggered.
- [ ] Set GPIB timeout to 3–5 seconds as a starting point on all instruments; note that 2182A and 2700 readings with high NPLC or filtering can require several seconds, so **tune timeout to be longer than longest legitimate operation, not a fixed rule**; retry once on timeout; fail hard if timeout persists.
- [ ] Enable Keithley 2700 open thermocouple detection (OTCD); read alarm status after each measurement; abort on any open.

**Data Integrity (DATA-1, DATA-3, DATA-4):**
- [ ] Implement temperature validation: range check, rate-of-change limit, stuck-value detector, open-thermocouple fallback (not 0 °C).
- [ ] Add per-run hash tracking: SHA-256 of raw data block, validate on re-open, warn if corrupted.
- [ ] Detect orphaned "running" state runs on startup; prompt user to resume/cancel/mark failed.
- [ ] Initialize Alembic; create first migration (baseline schema).

**Configuration (CFG-1, CFG-2):**
- [ ] Replace hardcoded GPIB addresses with pydantic config object loaded from `.toml` at startup.
- [ ] Store config in platformdirs user config directory (Windows: `%APPDATA%\V1_TE_measurements\config.toml`).
- [ ] Support per-rig profile switching via dropdown menu at startup.

**Testing & CI:**
- [ ] Set up GitHub Actions workflow: install Python, install dependencies, run pytest-qt headless, build PyInstaller .exe.
- [ ] Write 5–10 unit tests for physics calculations (Seebeck fit, resistivity formula, Smits correction).
- [ ] Write pyvisa-sim YAML for Keithley 2700 (basic SCPI responses); run measurement procedure against simulated instrument in CI.

**Estimated effort:** 80–120 hours. **Roadblock removal:** Once complete, software is safe for attended operation; Phase 2 hardware enables unattended.

### Phase 2 (Short-term, 2–4 weeks): Hardware Safety & Database Robustness
**Goal:** Meet IEC 61010-2-010 and enable unattended operation; establish data provenance.

**Hardware Safety (Independent Over-Temperature Protection):**
- [ ] Order and install **DC-rated thermal fuse** (trip temperature set ABOVE the lab's maximum planned operating temperature on the hot side, and BELOW the damage point for the sample, fixture, wiring and thermocouples; lab determines exact rating) in series with the heater fixture. Cost ~$15–30 depending on rating.
- [ ] Order **standalone over-temperature limit controller** with its own independent thermocouple input (NOT relying on the Keithley 2700 or software; examples: Omega CNi32, Chromalox, Watlow EZ-ZONE; cost ~$200–350). Configure setpoint at a safe temperature between normal operation maximum and sample damage point. Manual-reset mode (requires operator to acknowledge and manually reset after trip).
- [ ] Order **safety relay** (IEC 61508–compatible preferred; ~$80) + **DC-rated contactor** rated for the P4K-80M DC output current (1.3 A; ~$50–100). Wire the limit controller relay output to the safety relay input. Safety relay output energizes the DC contactor to cut power from the P4K-80M output.
- [ ] **Circuit topology**: P4K-80M 110V AC input → (optional AC branch disconnect) → Contactor coil (energized by safety relay) → P4K-80M internal DC output stage → DC Contactor → Thermal Fuse → Heater fixture. Alternatively, cut the 110V AC supply to the P4K-80M via AC-rated contactor driven by the safety relay; check Matsusada datasheet for external interlock/shutdown pins if available (if P4K-80M has a remote shutdown or interlock input, document and use it). **Do NOT make the hardware interlock depend on Keithley 2700 alarm outputs or any software signal**—the limit controller and contactor must operate entirely independently of the PC and remain active even if the PC crashes.
- [ ] Verify that the limit controller, contactor, and thermal fuse all operate independently and test each barrier: (1) manually trigger the limit controller to verify contactor de-energizes, (2) apply heat to thermal fuse to verify it trips, (3) cycle power multiple times to confirm the safeguards remain functional.
- [ ] Label all connections; photograph circuit for documentation; keep design documentation with the lab's safety files.

**Database & Data Management:**
- [ ] Enable SQLite WAL mode at connection time; handle `-wal` checkpoint recovery on startup.
- [ ] Add `audit_log` table: (log_id, run_id, timestamp, user, action, details, reason). Insert one entry per significant action—run start/stop/abort, settings changes, reprocessing, geometry/calibration updates, exports—never UPDATE/DELETE existing log entries. Commit to database on **every data point** (not every 50 rows) to minimize data loss on crash.
- [ ] Refactor data storage: raw (T1, T2, ΔT, V, I) as numeric columns in `data_points` table linked to run_id; compute Seebeck on-demand with provenance record.
- [ ] Implement HDF5 export: after run completion, serialize run metadata + results to HDF5 with NeXus attributes (operator, date, instrument serial, settings snapshot).
- [ ] Add local backup: auto-create daily backup in `%APPDATA%\V1_TE_measurements\backups\`, retention 30 days.

**Software Quality:**
- [ ] Configure Pyright (strict mode) in pyproject.toml; fix all type errors in codebase.
- [ ] Configure Ruff linter; run pre-commit hook (ruff check --fix).
- [ ] Extend pytest coverage to 70%+; add golden-file regression tests for known measurement datasets.
- [ ] Write documentation: two-page Quick Start PDF, troubleshooting Wiki page, in-app tooltips on all controls.

**Estimated effort:** 100–150 hours. **Outcome:** System is safe for unattended operation (Phase 1 + Phase 2 hardware tested and verified). Independent limit controller and thermal fuse provide protection that survives PC crash. Database migrations enable future schema changes without data loss.

### Phase 3 (Medium-term, 1–3 months): Reproducibility, Metadata, and Accreditation Evidence
**Goal:** Build audit trails and measurement reproducibility; prepare accreditation submission package.

**Measurement Reproducibility:**
- [ ] Require sample geometry input on every run (no 1×1×1 placeholders). Flag placeholder samples with `is_placeholder` boolean in metadata.
- [ ] Capture complete settings snapshot at run start/end (all Keithley parameters, heater setpoint, camera settings). Store in HDF5 NeXus attributes.
- [ ] Implement reprocessing: expose UI button "Reprocess with new geometry/calibration"; regenerate Seebeck/resistivity with updated parameters, store both versions with audit trail.
- [ ] Add operator name and sample ID as required fields (UI-7); disable Start button until filled.

**Measurement Validation:**
- [ ] Implement V-I curve pre-check before Seebeck measurement (contact quality gate). Display linear fit R² and contact resistance estimate.
- [ ] Add uncertainty budget per measurement: quantify cold-finger effect (FEA estimate or SRM 3451 calibration offset), thermal contact, probe spacing, thermocouple calibration. Compute combined uncertainty propagation per JCGM 100:2008.
- [ ] Run measurement with SRM 3451 (or reference material); compute systematic offset; store as calibration constant in config.

**Accreditation Package Assembly:**
- [ ] **Quality Manual**: written governance, roles, responsibilities, document control procedure.
- [ ] **Measurement Method Specification**: describe Seebeck differential method, temperature range, sample geometry requirements, uncertainty sources and magnitudes.
- [ ] **Software Validation Report**: V&V test plan, test results matrix, traceability of requirements to code to tests.
- [ ] **Hardware Safety Assessment**: FMEA table of failure modes, causes, current mitigation, residual risk; demonstration that thermal fuse + limit controller + relay meet IEC 61010-2-010.
- [ ] **Personnel Competency Records**: resumes, training completion, test scores of operators.
- [ ] **Equipment Calibration Records**: Keithley 2700 last factory calibration date, last NIST SRM 3451 verification date.
- [ ] **Procedure Execution Records**: at least 10 "reference runs" on stable sample, demonstrating consistent results, documented before/after instrument state.

**Estimated effort:** 120–180 hours. **Outcome:** Accreditation submission package complete. Internal audit against ISO 17025 checklist shows zero major findings.

### Phase 4 (Long-term, 3–6 months, optional): Cloud Integration, Remote Monitoring, and Community Contribution
**Goal:** Enable FAIR data sharing, unattended overnight runs with notifications, open-source sustainability.

**FAIR Data & NOMAD/ARIM Integration:**
- [ ] Implement NOMAD Metainfo serializer: convert run metadata + results to NOMAD-compatible JSON schema.
- [ ] Add "Push to NOMAD Lab" button (REST API call) after run completion; enable one-click FAIRification.
- [ ] Implement "Export as RO-Crate" for each run: generate RO-Crate metadata file (W3C PROV + software version + provenance chain) alongside HDF5 for long-term archival and re-executability.
- [ ] For Shizuoka: contact ARIM project office for ARIM-mdx direct integration (if available); implement push-to-ARIM button alongside NOMAD.

**Remote Monitoring & Unattended Operation:**
- [ ] Implement email/Slack notification on run completion or error (optional feature, default off for privacy).
- [ ] Add run queue: schedule multiple measurements sequentially, with pause/resume across power interruptions.
- [ ] USB hardware watchdog integration (Yocto-WatchdogDC, $100–150): PC must heartbeat every 5 seconds; watchdog cuts heater power on timeout (survives OS hang).
- [ ] Redundant thermocouple on sample: cross-check T1 vs. T2 every cycle; accept reading only if Δ < 2 °C.

**Open-Source Sustainability:**
- [ ] Publish JOSS (Journal of Open Source Software) paper describing software purpose, features, and research impact (typically 500 words). Archive on Zenodo; get DOI ([JOSS](https://joss.theoj.org/)).
- [ ] Contribute pyvisa-sim YAML profiles for Keithley 2700, 2182A, 2401, and Matsusada P4K-80M to community (enables other labs to test without hardware).
- [ ] Establish GitHub Issues for community contributions; welcome PRs for bug fixes, new instrument drivers, new measurement types.

**Japanese Localization:**
- [ ] Complete Qt Linguist i18n pipeline for Japanese; test with Japanese-fluent lab member.
- [ ] Translate troubleshooting documentation to Japanese.

**Estimated effort:** 150–220 hours. **Outcome:** Software is world-class, reproducible, shareable, and deployable to other institutions. Published paper establishes priority and credibility; JOSS citation improves grant competitiveness.

## Mapping Roadmap to Current Gaps: Every Finding in SOFTWARE_REVIEW.md Has a Solution Path

| SOFTWARE_REVIEW Finding | Severity | Roadmap Phase | Responsible Component | Implementation Note |
|---|---|---|---|---|
| **SAF-1: No over-temperature abort** | Critical | Phase 1 + Phase 2 | Software + Hardware | Phase 1: software T_MAX and dT/dt limits in config, abort if exceeded; Phase 2: independent limit controller and DC-rated thermal fuse |
| **SAF-2: Closing window mid-run leaves heater on** | Critical | Phase 1 | Software | closeEvent() handler detects active run, prompts user, stops session, waits for output_off() before closing window |
| **SAF-3: Sign Out during run** | High | Phase 1 | Software | Check measurement_active flag in logout handler; prompt user if run in progress |
| **SAF-4: GPIB hang blocks GUI** | High | Phase 1 | Software | Set VISA timeout to 3–5s as starting point (tune based on longest legitimate operation), retry once, fail hard; worker thread, never GUI thread |
| **SAF-5: Silent except:pass in shutdown** | High | Phase 1 | Software | Log all exceptions in shutdown path; retry remaining shutdown steps (do not re-raise and halt on first failure); alert user loudly if any step fails |
| **SAF-6: VISA objects shared, no lock** | Medium | Phase 1 | Software | Add QMutex per GPIB bus; serialize all VISA calls through mutex |
| **DATA-1: Failed TC read becomes 0 °C** | High | Phase 1 | Software | Range/rate/stuck validation; abort on plausibility failure; never fill-forward |
| **DATA-2: Runs without lab not saved** | High | Phase 1 | Software | Fix query condition: remove lab_id check; allow runs for any user |
| **DATA-3: Crash leaves "running" forever** | High | Phase 1+2 | Software + Database | Phase 1: detect orphaned runs at startup, prompt user to resume/cancel/mark failed; Phase 2: commit to DB on every data point (not every 50 rows) to minimize loss |
| **DATA-4: No schema migrations** | High | Phase 1 | Database | Initialize Alembic in Phase 1 (create baseline migration); full schema migration infrastructure in place for future changes |
| **DATA-5: DB save failure silent** | Medium | Phase 1 | Software | Raise exception on DB error; halt measurement; log to file |
| **DATA-6: No integrity hash for Seebeck** | Low | Phase 2 | Database | Add SHA-256 hash field to runs table; compute for all runs (not just I-V) |
| **CALC-1: Silent fallbacks (CF=1.0, blank ρ, blank S)** | High | Phase 3 | Software | Flag all fallbacks in metadata (e.g., `cf_is_fallback=True`, `cf_reason="probe < 3s"`); store both corrected and uncorrected results |
| **CALC-2: ΔT sign convention confusing** | Medium | Phase 3 | Software | Store thermocouple/voltage polarity per rig in config file (not UI toggle); record the sign convention and wiring in run metadata; validate sign with reference sample (e.g., constantan or NIST SRM 3451) |
| **CALC-3: No outlier rejection in Seebeck fit** | Medium | Phase 3 | Software | Add optional sigma-clipped or RANSAC fit; compare to linear; flag if residuals high |
| **CALC-4: Weak ohmic check** | Low | Phase 1 | Software | Require min. point count (e.g., 10) and max residual before declaring "ohmic"; report warning otherwise |
| **CFG-1: Settings don't persist** | High | Phase 1 | Software | Replace setattr in-memory hack with QSettings + pydantic config TOML file |
| **CFG-2: Everything hardcoded** | Medium | Phase 1 | Software | YAML config with all GPIB addresses, 2700 channels, heater limits, Optris SDK paths |
| **CFG-3: Address maps duplicated** | Medium | Phase 1 | Software | Single config.toml; all UI pages read from unified config object |
| **CFG-4: Dead 6221 legacy code** | Medium | Backlog | Code | Remove 6221 class and all dead branches; cleanup |
| **UI-1: GPIB scan on GUI thread** | Medium | Phase 1 | Software | Move ResourceManager scan to background worker; cache result for 30s; refresh on demand |
| **UI-2: Live charts re-plot full history** | Medium | Phase 1 | Software | Full dataset stored; decimate/downsampling for DISPLAY only (ring buffer of last 1000 visible points), dvg-pyqtgraph-threadsafe, autoDownsample; this prevents slowdown on long runs without data loss |
| **UI-3: History load synchronous** | Low | Phase 1 | Software | Background thread + progress bar (non-blocking) |
| **UI-4: Instrument names outdated** | Medium | Phase 1 | Software | Update dashboard labels from config.toml; verify against actual instruments on startup |
| **UI-5: Abort can't interrupt hung instrument** | Medium | Phase 1 | Software | Timeout + fail-safe; Abort flag only works between-cycle, not during hung VISA read |
| **UI-6: Errors hard to see** | Medium | Phase 3 | Software | Persistent status bar showing last 5 errors; expandable panel; per-instrument indicator lights |
| **UI-7: Metadata optional, unvalidated** | Medium | Phase 3 | Software | Sample ID and operator required; "Start" button disabled until filled |
| **UI-8: Geometry inputs allow near-zero** | Medium | Phase 3 | Software | Inline validation on input fields; error message; Start disabled if any ≤0 |
| **UI-9: Export code duplicated** | Medium | Phase 2 | Software | Consolidate PNG/CSV/Excel export into shared utility module called by all pages |
| **UI-10: Pillow found at export time** | Low | Phase 2 | Software | Pillow is already in requirements.txt and bundled by PyInstaller; verify availability at startup and remove the runtime fallback that delays the error |
| **UI-11: I-V chart no forward/reverse legend** | Low | Phase 1 | Software | Add legend or text label "Forward (Teal) / Reverse (Orange)" to chart; export with legend |
| **UI-12: Fixed pixel sizes** | Medium | Phase 1 | Software | Use QLayout managers instead of hardcoded sizes; test at 125–150% Windows scaling |
| **UI-13: Hard-coded colours bypass theme** | Low | Phase 1 | Software | Use palette() colors or qdarktheme; replace hardcoded #FF0000 with palette.color(QPalette.Highlight) |
| **UI-14: Colour-only cues** | Low | Phase 3 | Software | Add text labels to status cues ("Ready" label + green, not green-only) |
| **UI-15: Few tooltips and shortcuts** | Low | Phase 3 | Software | Add tooltip on every control; add Ctrl+S for Save, Ctrl+E for Export, F1 for Help |
| **CODE-1: Almost no tests** | Medium | Phase 1+2 | Testing | pytest-qt + pyvisa-sim; reach 70%+ coverage |
| **CODE-2: Very large functions** | Low | Phase 1 | Refactoring | Break _run_session into smaller Procedure classes (IVSweepProcedure, SeebeckProcedure, etc.) |

## Conclusion: The Path Forward Is Clear; Execution Requires 3–6 Months and ~$400 Hardware Investment

The convergence of **ISO 17025:2025 software validation mandates, IEC 61010-2-010 heating safety standards, and ALCOA+ data-integrity requirements** creates an unprecedented alignment: the same practices that earn lab accreditation also build world-class, reproducible science. The current TE measurement app is **not unsafe for attended operation** but is **critically unsafe for unattended** (no over-temperature cutoff, no watchdog) and **non-compliant with accreditation** (no audit trails, settings don't persist, no schema migrations, failed sensor reads become data). The gaps are **not design flaws but maturity stages**—every gap has a solution in either the standards literature, commercial instrument practice, or open-source frameworks.

**The recommended strategy is not a complete rewrite but disciplined refactoring into layers**: (1) **Phase 1 (2–4 weeks)** fixes safety and data-integrity bugs via software-only changes (software temperature limits, closeEvent handlers, sensor validation, GPIB timeouts, Alembic initialization, pydantic config); (2) **Phase 2 (2–4 weeks)** adds independent hardware interlocks (~$400: limit controller, DC-rated contactor, thermal fuse) and database robustness (WAL, audit logs, HDF5 export); (3) **Phase 3 (1–3 months)** builds measurement reproducibility and accreditation evidence (settings snapshots, reprocessing capability, uncertainty budgets, SRM 3451 calibration, quality manual and V&V documentation). **By end of Phase 1 + Phase 2 (4–8 weeks), the system becomes safe for unattended operation** (Phase 2 hardware is tested and independent). **By end of Phase 3, the system is ready for ISO 17025 accreditation submission** if that is desired (Phase 3 builds the formal documentation and evidence packages).

**Adoption of PyMeasure's Procedure/Experiment/Results/Worker architecture** decouples measurement logic from threading concerns and enables testing without hardware. **QCoDeS Station YAML configuration** solves hardcoded-addresses brittleness in one file per lab rig. **HDF5/NeXus + SQLite with Alembic + ALCOA+ audit logs** enable reproducible science and meet the quality benchmarks of ISO 17025. **Pytest-qt + pyvisa-sim** enable CI/CD testing without lab access, critical for small teams. **Phased delivery** allows the lab to continue operating while improvements land incrementally—Phase 1 improvements are safety and data-integrity enhancements all users benefit from immediately.

**For institutions pursuing world-class scientific quality**: execute Phase 1 + Phase 2 first (4–8 weeks). This establishes safety and reproducibility. Then Phase 3 can be tailored based on your goals: if ISO 17025 accreditation is desired, Phase 3 builds the formal evidence; if not, Phase 3 still adds measurement reproducibility (reprocessing, uncertainty budgets, SRM calibration) that strengthens research credibility. The ARIM-mdx and NOMAD ecosystems are available for FAIR data archival—coordinate with NIMS Data Integration Center (if using ARIM-mdx) to confirm metadata schema requirements before Phase 4 (this avoids Phase-3 rework). **Compared to commercial systems**, the evolved software will have fewer blind spots (commercial systems don't expose calibration workflows, remote monitoring, or audit trails as standard features), enabling academic differentiation and research quality that justifies the development investment.

---

## References and Key Sources

### Standards and Regulatory
- ISO/IEC 17025:2017 General requirements for the competence of testing and calibration laboratories [https://17025store.com/iso-iec-17025-2017-requirements/clause-7-process-requirements/]
- ISO/IEC 17025:2025 (effective Sept 27, 2025, transition through Sept 30, 2028) [https://intuitionlabs.ai/articles/iso-17025-laboratory-accreditation]
- IEC 61010-1:2010 Safety for electrical measurement, control, and laboratory equipment [https://standards.globalspec.com/std/13250090/iec-61010-1]
- IEC 61010-2-010:2020 Particular requirements for laboratory heating of materials [https://knowledge.bsigroup.com/products/safety-requirements-for-electrical-equipment-for-measurement-control-and-laboratory-use-particular-requirements-for-laboratory-equipment-for-the-heating-of-materials]
- IEC 61508:2010 Functional safety of electrical/electronic/programmable systems [https://en.wikipedia.org/wiki/IEC_61508]
- JCGM 100:2008 Guide to the Expression of Uncertainty in Measurement [https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf]
- GAMP 5 Computerized System Validation (2nd ed. 2022) [https://intuitionlabs.ai/pdfs/gamp-5-computerized-system-validation-in-pharma.pdf]

### NIST and Measurement Standards
- NIST SRM 3451 Low-Temperature Seebeck Coefficient Standard [https://tsapps.nist.gov/srmext/certificates/3451.pdf]
- NIST Thermoelectric Measurements Program [https://www.nist.gov/programs-projects/thermoelectric-measurements]
- Alleno et al. Interlaboratory Round-Robin Study [https://pubs.aip.org/aip/rsi/article-abstract/86/1/011301/360853]

### Data Standards and Metadata
- FAIR Data Guiding Principles [https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4792175/]
- HDF5 and NeXus [https://dawnsci.org/hdf5/]
- NOMAD Metainfo [https://arxiv.org/pdf/2205.14774]
- RO-Crate Provenance [https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0309210]
- ARIM-mdx Data System [https://arxiv.org/abs/2409.06734]

### Open-Source Frameworks
- PyMeasure [https://pymeasure.readthedocs.io/]
- QCoDeS [http://microsoft.github.io/Qcodes/]
- Bluesky [https://blueskyproject.io/]
- PyMoDAQ [https://pymodaq.cnrs.fr/]

### Commercial Systems
- Linseis LSR [https://www.linseis.com/en/instruments/lsr-thermoelectrics/]
- ULVAC ZEM-3 [https://showcase.ulvac.co.jp/en/products/heat-treatment-and-thermal-properties/thermoelectric-evaluation-device/thermoelectric-properties/zem-3series.html]
- Quantum Design PPMS [https://qdusa.com/]

### Python Tools and CI/CD
- pytest-qt [https://pypi.org/project/pytest-qt/]
- Pyright [https://pydevtools.com/handbook/reference/pyright/]
- Ruff [https://osquant.com/papers/python-tooling-in-2025/]
- Alembic [https://alembic.sqlalchemy.org/]
- pyvisa-sim [http://python-in-the-lab.blogspot.com/2015/02/pyvisa-sim-test-your-pyvisa.html]
- Tufup [https://github.com/dennisvang/tufup]
- aqtinstall [https://aqtinstall.readthedocs.io/]

### UX and Software Quality
- Berkeley Lab STRUDEL Project [https://crd.lbl.gov/news-and-publications/news/2024/berkeley-labs-strudel-project-brings-uxui-methods-to-scientific-software-design/]
- ISO 9241 (Wikipedia) [https://en.wikipedia.org/wiki/ISO_9241]
- IEC 62366 (Wikipedia) [https://en.wikipedia.org/wiki/IEC_62366]
- JOSS [https://joss.theoj.org/]

---

**Report Date:** October 2, 2026  
**For:** Shizuoka University MXene / Thermoelectric Laboratory  
**Prepared by:** Synthesis of research into standards, commercial benchmarks, open-source frameworks, and safety engineering.  
**Next Steps:** (1) Confirm university EHS policy on unattended heating and over-temperature protection requirements; (2) Prioritize Phase 1 software safety fixes (weeks 1–2: software temperature limits, closeEvent, GPIB timeouts, sensor validation, Alembic); (3) In parallel, order and plan Phase 2 hardware (limit controller, contactor, thermal fuse; week 2 order, week 4–6 installation and testing); (4) Execute Phase 2 hardware installation and database hardening (weeks 3–4); (5) Once Phase 1+2 are stable (4–8 weeks), begin Phase 3 if pursuing accreditation or advanced reproducibility (uncertainty budgets, reprocessing, SRM calibration, documentation).
