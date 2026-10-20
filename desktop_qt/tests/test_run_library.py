"""Run library: who sees which runs, the filters, the preview and the full view
(with its integrity check)."""

import hashlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("pytestqt")


def _seebeck_rows(n=40):
    rows = []
    for i in range(n):
        dt = -0.2 * i
        t1 = 30 + 0.2 * i
        rows.append({"Time [s]": 2.0 * i, "TEMF [mV]": 0.04 * dt, "Temp1 [oC]": t1,
                     "Temp2 [oC]": t1 + dt, "Delta Temp [oC]": dt, "T0 [oC]": t1 + dt / 2,
                     "T0 [K]": t1 + dt / 2 + 273.15, "S [µV/K]": 40.0, "branch": "heating"})
    return rows


IV_ROWS = [{"current": i * 1e-3, "voltage": i * 2e-3, "resistance": 2.0} for i in range(1, 8)]


@pytest.fixture
def library(app_db, make_user):
    """Two labs, three users and five runs with their readings."""
    from app.models.db_models import Lab, Measurement, MeasurementIntegrity, MeasurementRow

    _path, factory = app_db
    s = factory()
    lab_a, lab_b = Lab(name="A"), Lab(name="B")
    s.add_all([lab_a, lab_b])
    s.commit()
    ids = SimpleNamespace(lab_a=lab_a.id, lab_b=lab_b.id)
    s.close()
    ids.alice = make_user("alice", "researcher", ids.lab_a)
    ids.ann = make_user("ann", "lab_admin", ids.lab_a)
    ids.bea = make_user("bea", "researcher", ids.lab_b)

    now = datetime.now()
    runs = [  # (user, lab, type, status, sample, age days, rows, end_reason)
        (ids.alice, ids.lab_a, "seebeck", "finished", "Bi2Te3-01", 1, _seebeck_rows(), None),
        (ids.alice, ids.lab_a, "iv", "finished", "Cu-02", 2, IV_ROWS, None),
        (ids.alice, ids.lab_a, "seebeck", "aborted", "Bi2Te3-02", 40, _seebeck_rows(10),
         "Safety abort: T1 above 120 °C"),
        (ids.ann, ids.lab_a, "iv", "stopped", "Ti3C2-01", 3, IV_ROWS, "Stopped by user"),
        (ids.bea, ids.lab_b, "seebeck", "finished", "SnSe-01", 5, _seebeck_rows(), None),
    ]
    s = factory()
    for user, lab, typ, status, sample, age, rows, why in runs:
        m = Measurement(user_id=user, lab_id=lab, type=typ, status=status, sample_id=sample,
                        operator="op", started_at=now - timedelta(days=age),
                        finished_at=now - timedelta(days=age) + timedelta(minutes=5),
                        end_reason=why, params_json="{}")
        s.add(m)
        s.flush()
        for i, r in enumerate(rows):
            s.add(MeasurementRow(measurement_id=m.id, seq=i, data_json=json.dumps(r)))
        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
        s.add(MeasurementIntegrity(measurement_id=m.id,
                                   data_hash=hashlib.sha256(canonical.encode()).hexdigest()))
    s.commit()
    s.close()
    return ids


def _page(qtbot, uid, role, lab_id=None):
    from app.ui.pages.history_page import HistoryPage
    page = HistoryPage(SimpleNamespace(id=uid, username="u", role=role, lab_id=lab_id))
    qtbot.addWidget(page)
    page.show()
    return page


def _samples(page):
    out = []
    for r in range(page.table.rowCount()):
        if not page.table.isRowHidden(r):
            run = page._run_by_id(page.table.item(r, 0).data(256))   # Qt.UserRole
            out.append(run["sample"])
    return sorted(out)


def test_researchers_see_their_own_runs(qtbot, library):
    page = _page(qtbot, library.alice, "researcher", library.lab_a)
    assert _samples(page) == ["Bi2Te3-01", "Bi2Te3-02", "Cu-02"]


def test_lab_admins_see_their_lab(qtbot, library):
    page = _page(qtbot, library.ann, "lab_admin", library.lab_a)
    assert _samples(page) == ["Bi2Te3-01", "Bi2Te3-02", "Cu-02", "Ti3C2-01"]


def test_super_admin_sees_everything(qtbot, library):
    page = _page(qtbot, 999, "super_admin")
    assert len(_samples(page)) == 5


def test_filters(qtbot, library):
    page = _page(qtbot, 999, "super_admin")
    page.seg_type.setCurrentIndex(2)                       # I-V
    assert _samples(page) == ["Cu-02", "Ti3C2-01"]
    page.seg_type.setCurrentIndex(0)
    page.cb_status.setCurrentIndex(3)                      # aborted / error
    assert _samples(page) == ["Bi2Te3-02"]
    page.cb_status.setCurrentIndex(0)
    page.cb_period.setCurrentIndex(2)                      # last 30 days
    assert "Bi2Te3-02" not in _samples(page) and len(_samples(page)) == 4
    page.cb_period.setCurrentIndex(0)
    page.inp_search.setText("snse")
    assert _samples(page) == ["SnSe-01"]
    page.inp_search.setText("safety abort")                # end reason is searchable
    assert _samples(page) == ["Bi2Te3-02"]


def test_preview_follows_the_selection(qtbot, library):
    page = _page(qtbot, 999, "super_admin")
    row = next(r for r in range(page.table.rowCount())
               if page._run_by_id(page.table.item(r, 0).data(256))["sample"] == "Cu-02")
    page.table.selectRow(row)
    page._on_select()
    assert page.pv_stack.currentIndex() == 1


def test_full_view_checks_integrity(qtbot, library, app_db):
    from app.models.db_models import MeasurementRow
    page = _page(qtbot, 999, "super_admin")

    def open_sample(sample):
        row = next(r for r in range(page.table.rowCount())
                   if page._run_by_id(page.table.item(r, 0).data(256))["sample"] == sample)
        page._open_detail(row)
        win = page._detail_windows[-1]
        qtbot.addWidget(win)
        return win

    def chips(win):
        from app.ui.widgets.ui_kit import Chip
        return [c.text() for c in win.findChildren(Chip)]

    assert "Integrity verified" in chips(open_sample("Bi2Te3-01"))
    assert "Integrity verified" in chips(open_sample("Cu-02"))

    s = app_db[1]()                                        # change one stored reading
    mid = page._runs[[r["sample"] for r in page._runs].index("SnSe-01")]["id"]
    row = s.query(MeasurementRow).filter_by(measurement_id=mid, seq=0).one()
    row.data_json = json.dumps({**json.loads(row.data_json), "TEMF [mV]": 9.9})
    s.commit()
    s.close()
    assert "Integrity MISMATCH" in chips(open_sample("SnSe-01"))
