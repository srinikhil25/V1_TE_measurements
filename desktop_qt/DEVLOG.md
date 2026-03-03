# Development Log — TE Measurement Desktop (PyQt6)

Records decisions, discoveries, and sprint progress.

---

## Sprint 1 — Foundation
**Date:** 2026-03-02
**Status:** Complete

### Decision: Tauri → PyQt6

The previous Tauri scaffold was discarded because its UI layer is a WebView
(web technology inside a native shell), which still feels like a web app to the
operator.  PyQt6 renders real Qt widgets — the same toolkit used by professional
scientific desktop and lab software.

**Why PyQt6 wins for this project:**
- True native Windows controls — no browser engine anywhere
- Instrument code imported directly as Python modules — no HTTP sidecar, no ports
- `pyqtgraph` for live scientific charts (designed for real-time data; far faster than Recharts)
- Single `.exe` packaging via PyInstaller; no Rust toolchain required
- Auth and database code reused verbatim from the existing sidecar layer

### Architecture

```
desktop_qt/
├── main.py
└── app/
    ├── core/          database, security, paths
    ├── models/        SQLAlchemy ORM (Lab, User, Measurement …)
    ├── instruments/   instrument.py, session_manager.py, seebeck_analysis.py
    │                  (copied from backend — direct import, no HTTP)
    ├── services/      auth_service, measurement_service
    └── ui/
        ├── theme.py              colour tokens + global QSS
        ├── login_window.py       centred login card
        ├── main_window.py        sidebar + header + QStackedWidget
        ├── widgets/              sidebar, header_bar
        └── pages/                dashboard, seebeck, iv, history, users, settings
```

### UI Design Language

| Token | Value | Usage |
|---|---|---|
| Sidebar bg | `#111827` | Dark left panel |
| Sidebar active | `#2563EB` | Active nav item |
| Content bg | `#F3F4F6` | Page background |
| Card bg | `#FFFFFF` | All cards |
| Primary | `#2563EB` | Buttons, focus rings |
| Font | Segoe UI | Windows system font |

### Dev Accounts

| Username     | Password     | Role          |
|---|---|---|
| `superadmin` | `superadmin` | `super_admin` |
| `labadmin`   | `labadmin`   | `lab_admin`   |
| `researcher` | `researcher` | `researcher`  |

### Smoke Test

```
MainWindow OK — superadmin (super_admin)
MainWindow OK — labadmin   (lab_admin)
MainWindow OK — researcher (researcher)
All windows passed.
```

### Known gaps / next sprint
- Seebeck page: save completed sessions to `measurements` table in DB
- History page: export row to Excel
- IV page: export CSV / Excel
- Settings: persist GPIB overrides to config file (not just in-memory)
- PyInstaller `.exe` packaging script
- Polish: keyboard shortcuts, status-bar instrument live polling
