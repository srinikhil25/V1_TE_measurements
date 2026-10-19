"""Settings page — rig configuration (addresses, channels, limits), change password.

The rig configuration is stored in ``config.toml`` in the application data
folder (see ``app.core.config``). It is validated on save; changes apply from
the next measurement.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QMessageBox, QScrollArea,
    QSpinBox, QDoubleSpinBox, QCheckBox,
)
from PyQt6.QtCore import Qt

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG, PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, SUCCESS, ERROR, WARNING, WARNING_BG,
)

# Roles that may change the rig configuration (it affects every user's runs).
_CONFIG_ROLES = ("super_admin", "lab_admin")

_FIELD_STYLE = (
    f"QLineEdit {{ background: white; border: 1px solid {BORDER}; "
    f"border-radius: 6px; padding: 7px 10px; font-size: 13px; }}"
    f"QLineEdit:focus {{ border-color: {PRIMARY}; }}"
)
_BTN_PRIMARY = (
    f"QPushButton {{ background: {PRIMARY}; color: white; border: none; "
    f"border-radius: 6px; font-size: 13px; font-weight: 600; padding: 0 16px; }}"
    f"QPushButton:hover {{ background: #26606A; }}"
)
_BTN_SECONDARY = (
    f"QPushButton {{ background: white; color: {TEXT_SECONDARY}; "
    f"border: 1px solid {BORDER}; border-radius: 6px; font-size: 13px; "
    f"font-weight: 600; padding: 0 16px; }}"
    f"QPushButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}"
)


def _card(title: str) -> tuple:
    """Return (QFrame card, inner QVBoxLayout)."""
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet(
        f"QFrame#card {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
        f"border-radius: 8px; }}"
    )
    v = QVBoxLayout(f)
    v.setContentsMargins(20, 16, 20, 16)
    v.setSpacing(12)

    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
        f"letter-spacing: 1px; border: none; background: transparent;"
    )
    v.addWidget(lbl)
    return f, v


def _lbl(text: str, muted: bool = False) -> QLabel:
    l = QLabel(text)
    l.setWordWrap(muted)      # muted = hint text; wrap instead of widening the page
    color = TEXT_MUTED if muted else TEXT_SECONDARY
    l.setStyleSheet(f"color: {color}; font-size: 12px; border: none; background: transparent;")
    return l


def _sub(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 700; "
        f"border: none; padding-top: 6px; background: transparent;"
    )
    return l


def _note(text: str) -> QLabel:
    l = QLabel(text)
    l.setWordWrap(True)
    l.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
    return l


def _ispin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    w = QSpinBox()
    w.setRange(lo, hi)
    if suffix:
        w.setSuffix(suffix)
    w.setFixedHeight(34)
    w.setMinimumWidth(120)
    return w


def _dspin(lo: float, hi: float, decimals: int, suffix: str = "", step: float = 1.0) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    if suffix:
        w.setSuffix(suffix)
    w.setFixedHeight(34)
    w.setMinimumWidth(120)
    return w


class SettingsPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        # Scoped by object name so labels inside the white cards stay white.
        content.setObjectName("settingsContent")
        content.setStyleSheet(f"QWidget#settingsContent {{ background: {CONTENT_BG}; }}")
        v = QVBoxLayout(content)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(20)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)

        if self._user.role in _CONFIG_ROLES:
            v.addWidget(self._build_config_card())

        v.addWidget(self._build_password_card())
        v.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        scroll.viewport().setStyleSheet(f"background: {CONTENT_BG};")

    # ── Rig configuration card ───────────────────────────────────────────

    def _build_config_card(self) -> QFrame:
        from ...core.config import PK_RATED_CURRENT_A, PK_RATED_VOLTAGE_V, config_path
        from ...services.instrument_scan import INSTRUMENTS

        card, cv = _card("Rig Configuration")
        cv.addWidget(_note(
            f"Stored in {config_path()}. Changes apply from the next measurement "
            "(a run in progress keeps the settings it started with)."
        ))

        # Instruments: address + VISA timeout
        cv.addWidget(_sub("Instruments (GPIB address · VISA timeout)"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self._addr = {}
        self._timeout = {}
        for row, (key, _short, full, role) in enumerate(INSTRUMENTS):
            name = _lbl(full)
            name.setToolTip(role)
            addr = QLineEdit()
            addr.setStyleSheet(_FIELD_STYLE)
            addr.setFixedHeight(34)
            addr.setMinimumWidth(200)
            tmo = _ispin(500, 120_000, " ms")
            tmo.setSingleStep(1000)
            grid.addWidget(name, row, 0)
            grid.addWidget(addr, row, 1)
            grid.addWidget(tmo, row, 2)
            grid.addWidget(_lbl(role, muted=True), row, 3)
            self._addr[key] = addr
            self._timeout[key] = tmo
        grid.setColumnStretch(1, 1)
        cv.addLayout(grid)

        # Thermocouple channels
        cv.addWidget(_sub("Thermocouple channels (Keithley 2700 scanner)"))
        tcg = QGridLayout()
        tcg.setHorizontalSpacing(12)
        tcg.setVerticalSpacing(8)
        tcg.addWidget(_lbl("T1 (hot side)", muted=True), 0, 1)
        tcg.addWidget(_lbl("T2 (cold side)", muted=True), 0, 2)
        self._tc = {}
        for row, (mode, label) in enumerate((("in_plane", "In-plane"),
                                             ("out_plane", "Out-of-plane")), start=1):
            tcg.addWidget(_lbl(label), row, 0)
            for col, side in enumerate(("t1", "t2"), start=1):
                sb = _ispin(101, 240)
                tcg.addWidget(sb, row, col)
                self._tc[f"{mode}_{side}"] = sb
        tcg.setColumnStretch(3, 1)
        cv.addLayout(tcg)
        self.cb_otcd = QCheckBox("Open-thermocouple detection (a broken TC reads as overflow, "
                                 "so the safety layer can catch it)")
        self.cb_otcd.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        cv.addWidget(self.cb_otcd)

        # Heater limits
        cv.addWidget(_sub("Heater limits (Matsusada P4K-80M)"))
        hg = QGridLayout()
        hg.setHorizontalSpacing(12)
        hg.setVerticalSpacing(8)
        hg.addWidget(_lbl("Current limit", muted=True), 0, 1)
        hg.addWidget(_lbl("Max drive voltage", muted=True), 0, 2)
        self._heater = {}
        for row, (mode, label) in enumerate((("in_plane", "In-plane"),
                                             ("out_plane", "Out-of-plane")), start=1):
            hg.addWidget(_lbl(label), row, 0)
            cur = _dspin(0.01, PK_RATED_CURRENT_A, 3, " A", 0.05)
            vol = _dspin(0.1, PK_RATED_VOLTAGE_V, 1, " V", 1.0)
            hg.addWidget(cur, row, 1)
            hg.addWidget(vol, row, 2)
            self._heater[mode] = (cur, vol)
        hg.setColumnStretch(3, 1)
        cv.addLayout(hg)

        # Safety limits
        cv.addWidget(_sub("Software safety limits"))
        warn = QLabel(
            "These checks stop the heater only while this application is running. "
            "They are not a replacement for an independent hardware over-temperature "
            "cut-off. Set the maximum temperature above the hottest normal run and "
            "below the damage temperature of the sample, fixture, wiring and thermocouples."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(
            f"background: {WARNING_BG}; color: {WARNING}; border: 1px solid {WARNING}; "
            f"border-radius: 6px; padding: 8px 10px; font-size: 11px;"
        )
        cv.addWidget(warn)
        sg = QGridLayout()
        sg.setHorizontalSpacing(12)
        sg.setVerticalSpacing(8)
        self.sb_tmax = _dspin(20, 1000, 1, " °C")
        self.sb_rate = _dspin(0.1, 1000, 1, " °C/min")
        self.sb_window = _dspin(5, 600, 0, " s", 5)
        self.sb_invalid = _ispin(1, 20)
        self.sb_pmin = _dspin(-273, 1000, 1, " °C")
        self.sb_pmax = _dspin(-273, 2000, 1, " °C")
        rows = [
            ("Maximum temperature (any TC)", self.sb_tmax,
             "Run aborts and the heater switches off above this."),
            ("Maximum heating rate", self.sb_rate,
             "Aborts on faster heating (thermal runaway, poor contact)."),
            ("Heating-rate window", self.sb_window,
             "The rate is measured over this time span."),
            ("Invalid readings before abort", self.sb_invalid,
             "Consecutive cycles with a missing / open / implausible TC."),
            ("Plausible range — min", self.sb_pmin,
             "Readings outside the range are invalid (never used as data)."),
            ("Plausible range — max", self.sb_pmax, ""),
        ]
        for r, (label, w, hint) in enumerate(rows):
            sg.addWidget(_lbl(label), r, 0)
            sg.addWidget(w, r, 1)
            sg.addWidget(_lbl(hint, muted=True), r, 2)
        sg.setColumnStretch(2, 1)
        cv.addLayout(sg)

        self.lbl_cfg_msg = QLabel("")
        self.lbl_cfg_msg.setWordWrap(True)
        self.lbl_cfg_msg.setStyleSheet(f"color: {ERROR}; font-size: 12px; border: none; background: transparent;")
        cv.addWidget(self.lbl_cfg_msg)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Configuration")
        btn_save.setFixedHeight(36)
        btn_save.setStyleSheet(_BTN_PRIMARY)
        btn_save.clicked.connect(self._save_config)
        btn_revert = QPushButton("Revert")
        btn_revert.setFixedHeight(36)
        btn_revert.setStyleSheet(_BTN_SECONDARY)
        btn_revert.setToolTip("Discard unsaved edits and show the saved configuration.")
        btn_revert.clicked.connect(self._load_config_into_form)
        btn_defaults = QPushButton("Restore Defaults")
        btn_defaults.setFixedHeight(36)
        btn_defaults.setStyleSheet(_BTN_SECONDARY)
        btn_defaults.setToolTip("Fill the form with the built-in defaults (not saved until you click Save).")
        btn_defaults.clicked.connect(self._fill_defaults)
        btns.addWidget(btn_save)
        btns.addWidget(btn_revert)
        btns.addWidget(btn_defaults)
        btns.addStretch()
        cv.addLayout(btns)

        self._load_config_into_form()
        return card

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
        self.sb_pmin.setValue(s.plausible_min_C)
        self.sb_pmax.setValue(s.plausible_max_C)

    def _load_config_into_form(self) -> None:
        from ...core.config import get_config, load_warnings
        self._set_form(get_config())
        problems = load_warnings()
        if problems:
            self.lbl_cfg_msg.setStyleSheet(f"color: {ERROR}; font-size: 12px; border: none; background: transparent;")
            self.lbl_cfg_msg.setText(
                "The config file has problems, so defaults are shown and in use. "
                "Saving rewrites the file:\n• " + "\n• ".join(problems))
        else:
            self.lbl_cfg_msg.setText("")

    def _fill_defaults(self) -> None:
        from ...core.config import AppConfig
        self._set_form(AppConfig())
        self.lbl_cfg_msg.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; border: none; background: transparent;")
        self.lbl_cfg_msg.setText("Defaults filled in — click Save Configuration to keep them.")

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
        s.plausible_min_C = float(self.sb_pmin.value())
        s.plausible_max_C = float(self.sb_pmax.value())
        return cfg

    def _save_config(self) -> None:
        from ...core.config import ConfigError, save_config
        import logging
        cfg = self._form_to_config()
        try:
            save_config(cfg)
        except ConfigError as exc:
            self.lbl_cfg_msg.setStyleSheet(f"color: {ERROR}; font-size: 12px; border: none; background: transparent;")
            self.lbl_cfg_msg.setText("Not saved:\n• " + "\n• ".join(exc.problems))
            return
        except OSError as exc:
            QMessageBox.critical(self, "Not saved", f"Could not write the config file:\n{exc}")
            return
        logging.getLogger(__name__).info(
            "Rig configuration saved by %s", getattr(self._user, "username", "?"))
        self.lbl_cfg_msg.setStyleSheet(f"color: {SUCCESS}; font-size: 12px; border: none; background: transparent;")
        self.lbl_cfg_msg.setText("Saved. Applies from the next measurement.")

    # ── Change password card ─────────────────────────────────────────────

    def _build_password_card(self) -> QFrame:
        card, cv = _card("Change Password")

        self.inp_old = QLineEdit()
        self.inp_old.setPlaceholderText("Current password")
        self.inp_old.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_old.setFixedHeight(36)
        self.inp_old.setMaximumWidth(400)
        self.inp_old.setStyleSheet(_FIELD_STYLE)

        self.inp_new1 = QLineEdit()
        self.inp_new1.setPlaceholderText("New password")
        self.inp_new1.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_new1.setFixedHeight(36)
        self.inp_new1.setMaximumWidth(400)
        self.inp_new1.setStyleSheet(_FIELD_STYLE)

        self.inp_new2 = QLineEdit()
        self.inp_new2.setPlaceholderText("Confirm new password")
        self.inp_new2.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_new2.setFixedHeight(36)
        self.inp_new2.setMaximumWidth(400)
        self.inp_new2.setStyleSheet(_FIELD_STYLE)

        for label, widget in [
            ("Current password", self.inp_old),
            ("New password",     self.inp_new1),
            ("Confirm new",      self.inp_new2),
        ]:
            cv.addWidget(_lbl(label))
            cv.addWidget(widget)

        self.lbl_pw_msg = QLabel("")
        self.lbl_pw_msg.setStyleSheet(f"color: {ERROR}; font-size: 12px; border: none; background: transparent;")
        cv.addWidget(self.lbl_pw_msg)

        btn = QPushButton("Change Password")
        btn.setFixedHeight(36)
        btn.setFixedWidth(180)
        btn.setStyleSheet(_BTN_PRIMARY)
        btn.clicked.connect(self._change_password)
        cv.addWidget(btn)

        return card

    def _change_password(self):
        old   = self.inp_old.text()
        new1  = self.inp_new1.text()
        new2  = self.inp_new2.text()

        if not old or not new1:
            self.lbl_pw_msg.setText("All fields are required.")
            return
        if new1 != new2:
            self.lbl_pw_msg.setText("New passwords do not match.")
            return
        if len(new1) < 6:
            self.lbl_pw_msg.setText("Password must be at least 6 characters.")
            return

        from ...services.auth_service import change_password
        ok = change_password(self._user.id, old, new1)
        if ok:
            self.lbl_pw_msg.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px; border: none;"
            )
            self.lbl_pw_msg.setText("Password changed successfully.")
            self.inp_old.clear()
            self.inp_new1.clear()
            self.inp_new2.clear()
        else:
            self.lbl_pw_msg.setStyleSheet(
                f"color: {ERROR}; font-size: 12px; border: none;"
            )
            self.lbl_pw_msg.setText("Incorrect current password.")
