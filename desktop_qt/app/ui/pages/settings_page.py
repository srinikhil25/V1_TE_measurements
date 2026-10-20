"""Settings — rig configuration (addresses, channels, limits) and account.

The rig configuration is stored in ``config.toml`` in the application data
folder (see ``app.core.config``). It is validated on save; changes apply from
the next measurement.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import theme as T
from ..widgets.ui_kit import (
    Callout,
    Panel,
    button,
    field,
    label,
    page_scaffold,
    set_props,
)

# Roles that may change the rig configuration (it affects every user's runs).
_CONFIG_ROLES = ("super_admin", "lab_admin")


def _ispin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    w = QSpinBox()
    w.setRange(lo, hi)
    if suffix:
        w.setSuffix(suffix)
    w.setProperty("mono", True)
    w.setMinimumWidth(130)
    return w


def _dspin(lo: float, hi: float, decimals: int, suffix: str = "", step: float = 1.0) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setDecimals(decimals)
    w.setRange(lo, hi)
    w.setSingleStep(step)
    if suffix:
        w.setSuffix(suffix)
    w.setProperty("mono", True)
    w.setMinimumWidth(130)
    return w


def _form_row(grid: QGridLayout, r: int, title: str, widget: QWidget, hint: str = ""):
    col = QVBoxLayout()
    col.setSpacing(1)
    col.addWidget(label(title, "body"))
    if hint:
        col.addWidget(label(hint, "caption", wrap=True))
    grid.addLayout(col, r, 0)
    grid.addWidget(widget, r, 1, Qt.AlignmentFlag.AlignTop)


class SettingsPage(QWidget):
    config_saved = pyqtSignal()

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._sections = []
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        can_config = self._user.role in _CONFIG_ROLES
        tb, body = page_scaffold(
            self, "Settings",
            "Rig configuration and your account" if can_config else "Your account")
        self.toolbar = tb

        row = QHBoxLayout()
        row.setSpacing(16)

        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
        self.nav.setProperty("flat", False)
        self.nav.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; }}"
            f"QListWidget::item {{ min-height: 32px; padding: 0 10px; border-radius: 4px; "
            f"color: {T.TEXT_SECONDARY}; }}"
            f"QListWidget::item:hover {{ background: {T.SURFACE_SUNKEN}; color: {T.TEXT_PRIMARY}; }}"
            f"QListWidget::item:selected {{ background: {T.SURFACE}; color: {T.ACCENT_TEXT}; "
            f"font-weight: 600; border: 1px solid {T.BORDER}; }}")
        self.nav.currentRowChanged.connect(self._jump)
        row.addWidget(self.nav, 0, Qt.AlignmentFlag.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._content_v = QVBoxLayout(content)
        self._content_v.setContentsMargins(0, 0, 8, 16)
        self._content_v.setSpacing(16)
        self.scroll_area.setWidget(content)
        right.addWidget(self.scroll_area, 1)

        if can_config:
            save_bar = self._build_save_bar()     # holds lbl_cfg_msg used while loading
            self._build_config_sections()
            right.addWidget(save_bar)
        self._add_section("Account", self._build_password_card())
        self._content_v.addStretch()

        holder = QWidget()
        holder.setMaximumWidth(980)
        holder.setLayout(right)
        row.addWidget(holder, 1)
        row.addStretch(0)
        body.addLayout(row, 1)
        self.nav.setCurrentRow(0)

    def _add_section(self, name: str, panel: QWidget):
        self._sections.append(panel)
        QListWidgetItem(name, self.nav)
        self._content_v.addWidget(panel)

    def _jump(self, idx: int):
        if 0 <= idx < len(self._sections):
            w = self._sections[idx]
            self.scroll_area.verticalScrollBar().setValue(w.y())

    # ── Rig configuration ────────────────────────────────────────────
    def _build_config_sections(self):
        from ...core.config import PK_RATED_CURRENT_A, PK_RATED_VOLTAGE_V, config_path
        from ...services.instrument_scan import INSTRUMENTS

        # Instruments
        p = Panel("Instruments", "GPIB address and VISA timeout for each instrument")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(label("Instrument", "overline"), 0, 0)
        grid.addWidget(label("Address", "overline"), 0, 1)
        grid.addWidget(label("Timeout", "overline"), 0, 2)
        self._addr = {}
        self._timeout = {}
        for r, (key, _short, full, role) in enumerate(INSTRUMENTS, start=1):
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(full, "body"))
            col.addWidget(label(role, "caption"))
            addr = QLineEdit()
            addr.setProperty("mono", True)
            addr.setMinimumWidth(220)
            addr.textEdited.connect(lambda _t, w=addr: set_props(w, invalid=False))
            tmo = _ispin(500, 120_000, " ms")
            tmo.setSingleStep(1000)
            grid.addLayout(col, r, 0)
            grid.addWidget(addr, r, 1)
            grid.addWidget(tmo, r, 2)
            self._addr[key] = addr
            self._timeout[key] = tmo
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        p.body.addLayout(grid)
        p.body.addWidget(label(f"Stored in {config_path()}. Changes apply from the next "
                               "measurement; a run in progress keeps its settings.",
                               "caption", wrap=True))
        self._add_section("Instruments", p)

        # Thermocouples
        p = Panel("Thermocouples", "Keithley 2700 scanner channels")
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        g.addWidget(label("Geometry", "overline"), 0, 0)
        g.addWidget(label("T₁ hot side", "overline"), 0, 1)
        g.addWidget(label("T₂ cold side", "overline"), 0, 2)
        self._tc = {}
        for r, (mode, text) in enumerate((("in_plane", "In-plane"), ("out_plane", "Out-of-plane")),
                                         start=1):
            g.addWidget(label(text, "body"), r, 0)
            for c, side in enumerate(("t1", "t2"), start=1):
                sb = _ispin(101, 240)
                g.addWidget(sb, r, c)
                self._tc[f"{mode}_{side}"] = sb
        g.setColumnStretch(3, 1)
        p.body.addLayout(g)
        self.cb_otcd = QCheckBox("Open-thermocouple detection")
        p.body.addWidget(self.cb_otcd)
        p.body.addWidget(label("A broken thermocouple then reads as overflow, so the safety "
                               "checks can catch it.", "caption", wrap=True))
        self._add_section("Thermocouples", p)

        # Heater limits
        p = Panel("Heater limits", "Matsusada P4K-80M — per sample geometry")
        hg = QGridLayout()
        hg.setHorizontalSpacing(12)
        hg.setVerticalSpacing(10)
        hg.addWidget(label("Geometry", "overline"), 0, 0)
        hg.addWidget(label("Current limit", "overline"), 0, 1)
        hg.addWidget(label("Max drive voltage", "overline"), 0, 2)
        self._heater = {}
        for r, (mode, text) in enumerate((("in_plane", "In-plane"), ("out_plane", "Out-of-plane")),
                                         start=1):
            hg.addWidget(label(text, "body"), r, 0)
            cur = _dspin(0.01, PK_RATED_CURRENT_A, 3, " A", 0.05)
            vol = _dspin(0.1, PK_RATED_VOLTAGE_V, 1, " V", 1.0)
            hg.addWidget(cur, r, 1)
            hg.addWidget(vol, r, 2)
            self._heater[mode] = (cur, vol)
        hg.setColumnStretch(3, 1)
        p.body.addLayout(hg)
        p.body.addWidget(label(f"Supply rating: {PK_RATED_CURRENT_A:g} A / {PK_RATED_VOLTAGE_V:g} V.",
                               "caption"))
        self._add_section("Heater limits", p)

        # Safety
        p = Panel("Safety limits", "Software checks run on every reading")
        p.body.addWidget(Callout(
            "These checks stop the heater only while this application is running. They do not "
            "replace an independent hardware over-temperature cut-off. Set the maximum "
            "temperature above the hottest normal run and below the damage temperature of the "
            "sample, fixture, wiring and thermocouples.", "warning", title="Not a hardware interlock"))
        sg = QGridLayout()
        sg.setHorizontalSpacing(24)
        sg.setVerticalSpacing(12)
        self.sb_tmax = _dspin(20, 1000, 1, " °C")
        self.sb_rate = _dspin(0.1, 1000, 1, " °C/min")
        self.sb_window = _dspin(5, 600, 0, " s", 5)
        self.sb_invalid = _ispin(1, 20)
        self.sb_identical = _ispin(0, 1000)
        self.sb_identical.setSpecialValueText("off")
        self.sb_pmin = _dspin(-273, 1000, 1, " °C")
        self.sb_pmax = _dspin(-273, 2000, 1, " °C")
        rows = [
            ("Maximum temperature (any TC)", self.sb_tmax,
             "The run aborts and the heater switches off above this."),
            ("Maximum heating rate", self.sb_rate,
             "Aborts on faster heating (thermal runaway, poor contact)."),
            ("Heating-rate window", self.sb_window, "The rate is measured over this time span."),
            ("Invalid readings before abort", self.sb_invalid,
             "Consecutive cycles with a missing, open or implausible thermocouple."),
            ("Identical readings = stuck sensor", self.sb_identical,
             "A live thermocouple always shows last-digit noise; this many identical readings in "
             "a row marks the channel invalid (0 = off)."),
            ("Plausible range — minimum", self.sb_pmin,
             "Readings outside the range are invalid and never used as data."),
            ("Plausible range — maximum", self.sb_pmax, ""),
        ]
        for r, (title, w, hint) in enumerate(rows):
            _form_row(sg, r, title, w, hint)
        sg.setColumnStretch(0, 1)
        p.body.addLayout(sg)
        self._add_section("Safety limits", p)

        self._load_config_into_form()

    def _build_save_bar(self) -> QFrame:
        bar = QFrame()
        bar.setProperty("panel", True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        self.lbl_cfg_msg = label("", "caption", wrap=True)
        lay.addWidget(self.lbl_cfg_msg, 1)
        btn_defaults = button("Restore defaults", "ghost",
                              tooltip="Fill the form with the built-in defaults (not saved until you click Save).")
        btn_defaults.clicked.connect(self._fill_defaults)
        btn_revert = button("Revert", tooltip="Discard unsaved edits and show the saved configuration.")
        btn_revert.clicked.connect(self._load_config_into_form)
        btn_save = button("Save configuration", "primary", icon="save")
        btn_save.clicked.connect(self._save_config)
        lay.addWidget(btn_defaults)
        lay.addWidget(btn_revert)
        lay.addWidget(btn_save)
        return bar

    def _msg(self, text: str, kind: str = "muted"):
        role = {"error": "error", "success": "success"}.get(kind, "caption")
        set_props(self.lbl_cfg_msg, role=role)
        self.lbl_cfg_msg.setText(text)

    def _set_form(self, cfg) -> None:
        for key, w in self._addr.items():
            w.setText(getattr(cfg.instruments, key))
        for key, w in self._timeout.items():
            w.setValue(int(getattr(cfg.visa_timeout_ms, key)))
        for name, w in self._tc.items():
            w.setValue(int(getattr(cfg.thermocouples, name)))
        self.cb_otcd.setChecked(bool(cfg.thermocouples.open_tc_detect))
        for mode, (cur, vol) in self._heater.items():
            lim = getattr(cfg.heater, mode)
            cur.setValue(lim.current_max_A)
            vol.setValue(lim.voltage_drive_max_V)
        s = cfg.safety
        self.sb_tmax.setValue(s.max_temperature_C)
        self.sb_rate.setValue(s.max_rise_rate_C_per_min)
        self.sb_window.setValue(s.rate_window_s)
        self.sb_invalid.setValue(int(s.max_consecutive_invalid_reads))
        self.sb_identical.setValue(int(s.max_identical_reads))
        self.sb_pmin.setValue(s.plausible_min_C)
        self.sb_pmax.setValue(s.plausible_max_C)

    def _load_config_into_form(self) -> None:
        from ...core.config import get_config, load_warnings
        self._set_form(get_config())
        problems = load_warnings()
        if problems:
            self._msg("The config file has problems, so defaults are shown and in use. "
                      "Saving rewrites the file:\n• " + "\n• ".join(problems), "error")
        else:
            self._msg("All changes saved." if hasattr(self, "_saved_once") else
                      "Edit the values, then save. Changes apply from the next measurement.")

    def _fill_defaults(self) -> None:
        from ...core.config import AppConfig
        self._set_form(AppConfig())
        self._msg("Defaults filled in — click Save configuration to keep them.")

    def _form_to_config(self):
        from ...core.config import get_config
        cfg = get_config().copy()
        for key, w in self._addr.items():
            setattr(cfg.instruments, key, w.text().strip())
        for key, w in self._timeout.items():
            setattr(cfg.visa_timeout_ms, key, int(w.value()))
        for name, w in self._tc.items():
            setattr(cfg.thermocouples, name, int(w.value()))
        cfg.thermocouples.open_tc_detect = self.cb_otcd.isChecked()
        for mode, (cur, vol) in self._heater.items():
            lim = getattr(cfg.heater, mode)
            lim.current_max_A = float(cur.value())
            lim.voltage_drive_max_V = float(vol.value())
        s = cfg.safety
        s.max_temperature_C = float(self.sb_tmax.value())
        s.max_rise_rate_C_per_min = float(self.sb_rate.value())
        s.rate_window_s = float(self.sb_window.value())
        s.max_consecutive_invalid_reads = int(self.sb_invalid.value())
        s.max_identical_reads = int(self.sb_identical.value())
        s.plausible_min_C = float(self.sb_pmin.value())
        s.plausible_max_C = float(self.sb_pmax.value())
        return cfg

    def _save_config(self) -> None:
        import logging

        from ...core import audit
        from ...core.config import ConfigError, diff_configs, get_config, load_warnings, save_config
        old = get_config()
        cfg = self._form_to_config()
        changes = diff_configs(old, cfg)
        # A broken file on disk (defaults in use) must still be rewritable.
        if not changes and not load_warnings():
            self._msg("No changes to save.")
            return
        try:
            save_config(cfg)
        except ConfigError as exc:
            self._msg("Not saved:\n• " + "\n• ".join(exc.problems), "error")
            return
        except OSError as exc:
            QMessageBox.critical(self, "Not saved", f"Could not write the config file:\n{exc}")
            return
        logging.getLogger(__name__).info(
            "Rig configuration saved by %s: %s", getattr(self._user, "username", "?"), changes)
        audit.record("config_changed", details={"changes": changes})
        self._saved_once = True
        self._msg(f"Saved {len(changes)} change(s). Applies from the next measurement.", "success")
        self.config_saved.emit()

    # ── Account ──────────────────────────────────────────────────────
    def _build_password_card(self) -> Panel:
        from ..widgets.ui_kit import ROLE_LABELS
        p = Panel("Account", f"Signed in as {self._user.username} · "
                             f"{ROLE_LABELS.get(self._user.role, self._user.role)}")
        p.body.addWidget(label("CHANGE PASSWORD", "overline"))
        self.inp_old = QLineEdit()
        self.inp_old.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_new1 = QLineEdit()
        self.inp_new1.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_new1.setPlaceholderText("At least 6 characters")
        self.inp_new2 = QLineEdit()
        self.inp_new2.setEchoMode(QLineEdit.EchoMode.Password)
        form = QWidget()
        form.setMaximumWidth(380)
        fl = QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)
        fl.addWidget(field("Current password", self.inp_old))
        fl.addWidget(field("New password", self.inp_new1))
        fl.addWidget(field("Confirm new password", self.inp_new2))
        self.lbl_pw_msg = label("", "error", wrap=True)
        fl.addWidget(self.lbl_pw_msg)
        btn = button("Change password", "primary", icon="key")
        btn.clicked.connect(self._change_password)
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addStretch()
        fl.addLayout(row)
        p.body.addWidget(form)
        return p

    def _pw_msg(self, text: str, ok: bool = False):
        set_props(self.lbl_pw_msg, role="success" if ok else "error")
        self.lbl_pw_msg.setText(text)

    def _change_password(self):
        old = self.inp_old.text()
        new1 = self.inp_new1.text()
        new2 = self.inp_new2.text()

        if not old or not new1:
            self._pw_msg("All fields are required.")
            return
        if new1 != new2:
            self._pw_msg("The new passwords do not match.")
            return
        if len(new1) < 6:
            self._pw_msg("The password must be at least 6 characters.")
            return

        from ...services.auth_service import change_password
        if change_password(self._user.id, old, new1):
            self._pw_msg("Password changed.", ok=True)
            self.inp_old.clear()
            self.inp_new1.clear()
            self.inp_new2.clear()
        else:
            self._pw_msg("The current password is incorrect.")
