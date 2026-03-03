"""Measurement History page — list of past sessions from the database."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
)
from PyQt6.QtCore import Qt

from ..theme import (
    CARD_BG, BORDER, CONTENT_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)


class HistoryPage(QWidget):

    def __init__(self, user):
        super().__init__()
        self._user = user
        self._build_ui()
        self._load()

    def _build_ui(self):
        self.setStyleSheet(f"background: {CONTENT_BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Measurement History")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700; border: none;"
        )
        header.addWidget(title)
        header.addStretch()
        v.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "Type", "Sample ID", "Operator", "Status", "Started"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {CARD_BG}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; font-size: 13px; }}"
            f"QTableWidget::item:alternate {{ background: #F9FAFB; }}"
        )
        v.addWidget(self.table)

    def _load(self):
        from ...core.database import SessionLocal
        from ...models.db_models import Measurement

        db = SessionLocal()
        try:
            role = self._user.role
            uid  = self._user.id
            q = db.query(Measurement)
            if role == "researcher":
                q = q.filter_by(user_id=uid)
            elif role == "lab_admin":
                q = q.filter_by(lab_id=self._user.lab_id)
            rows = q.order_by(Measurement.started_at.desc()).limit(200).all()

            self.table.setRowCount(len(rows))
            for i, m in enumerate(rows):
                for col, val in enumerate([
                    str(m.id),
                    m.type,
                    m.sample_id or "—",
                    m.operator  or "—",
                    m.status,
                    m.started_at.strftime("%Y-%m-%d %H:%M") if m.started_at else "—",
                ]):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                    )
                    self.table.setItem(i, col, item)
        finally:
            db.close()
