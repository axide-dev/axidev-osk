from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout

from ..layouts.us_iso import build_us_iso_layout
from ..models import KeySpec
from .key_button import create_key_button, refresh_key_button


class KeyboardWidget(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self._latched_keys: dict[str, bool] = {"shift": False, "caps": False}
        self._latch_groups: dict[str, list[QPushButton]] = {"shift": [], "caps": []}

        self.setObjectName("keyboard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QVBoxLayout(self)
        container.setContentsMargins(18, 18, 18, 18)
        container.setSpacing(10)

        for row in build_us_iso_layout():
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            for spec in row:
                button = self._build_key(spec)
                row_layout.addWidget(button, int(spec.width * 10))

            container.addLayout(row_layout)

    def _build_key(self, spec: KeySpec) -> QPushButton:
        on_latch = None
        on_unlatch = None
        latched = False

        if spec.latchable and spec.key_id is not None:
            on_latch = lambda key_id=spec.key_id: self.set_latched_state(key_id, True)
            on_unlatch = lambda key_id=spec.key_id: self.set_latched_state(key_id, False)
            latched = self._latched_keys.get(spec.key_id, False)

        button = create_key_button(
            spec.label,
            width=spec.width,
            secondary_label=spec.secondary_label,
            key_id=spec.key_id,
            latchable=spec.latchable,
            latched=latched,
            on_latch=on_latch,
            on_unlatch=on_unlatch,
        )

        if spec.latchable and spec.key_id is not None:
            self._latch_groups.setdefault(spec.key_id, []).append(button)

        return button

    def set_latched_state(self, key_id: str, latched: bool) -> None:
        self._latched_keys[key_id] = latched
        for button in self._latch_groups.get(key_id, []):
            refresh_key_button(button, latched)
