"""Decode a plain root config into typed profile records.

The root config is plain data plus functions:

    {
        "active_profile": "default",
        "profiles": {
            "default": {
                "state": {...},
                "theme": {"qss": "..."},
                "windows": [...],
                "attachments": [...],
                "on": {"hot_corner.triggered": fn, ...},
            },
        },
    }

Node kinds and attachment kinds register how their options decode. The
decoder here owns everything common to every kind: IDs, style, bindings,
callbacks, children, and grid cells.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from ..messages import DataMap, DataValue
from ..runtime.functions import FunctionRef, FunctionRegistry
from .models import AlwaysOnTopWindowConfig, ChromeConfig, OverlayConfig, OverlayPlacement
from .reader import Bindable, ConfigError, ConfigReader


@dataclass(frozen=True, slots=True)
class PropertySpec:
    """One bindable node property and the plain type its values must have."""

    value_type: type | tuple[type, ...]
    default: DataValue = None


class NodeKindSpec(Protocol):
    """What the profile decoder needs to know about one node kind."""

    @property
    def properties(self) -> Mapping[str, PropertySpec]: ...

    @property
    def callbacks(self) -> Mapping[str, str]:
        """Map config callback fields such as ``on_press`` to event names."""
        ...

    @property
    def has_children(self) -> bool: ...

    def decode_options(self, reader: ConfigReader, /) -> object: ...


class AttachmentKindSpec(Protocol):
    def decode_options(self, reader: ConfigReader, /) -> object: ...


@dataclass(frozen=True, slots=True)
class StyleConfig:
    object_name: str | None = None
    classes: tuple[str, ...] = ()
    properties: DataMap = field(default_factory=dict)
    qss: str | None = None


@dataclass(frozen=True, slots=True)
class GridCell:
    row: int
    column: int
    row_span: int = 1
    column_span: int = 1


@dataclass(frozen=True, slots=True)
class NodeConfig:
    """One decoded node. Kind-specific settings live in ``options``."""

    kind: str
    id: str
    style: StyleConfig
    options: object
    bindings: Mapping[str, Bindable]
    callbacks: Mapping[str, FunctionRef]
    children: tuple["NodeConfig", ...] = ()
    cell: GridCell | None = None
    stretch: int = 0

    def walk(self) -> "list[NodeConfig]":
        nodes: list[NodeConfig] = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes


@dataclass(frozen=True, slots=True)
class WindowConfig:
    id: str
    title: str
    content: NodeConfig
    style: StyleConfig
    opacity: float = 1.0
    show_on_start: bool = False
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    minimum_size: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class AttachmentConfig:
    kind: str
    id: str
    options: object


@dataclass(frozen=True, slots=True)
class ThemeConfig:
    qss: str = ""


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    id: str
    state: DataMap
    theme: ThemeConfig
    windows: tuple[WindowConfig, ...]
    attachments: tuple[AttachmentConfig, ...]
    on: Mapping[str, tuple[FunctionRef, ...]]

    def window(self, window_id: str) -> WindowConfig:
        for window in self.windows:
            if window.id == window_id:
                return window
        raise LookupError(f"Profile {self.id!r} has no window {window_id!r}")

    def nodes(self) -> list[NodeConfig]:
        return [node for window in self.windows for node in window.content.walk()]


@dataclass(frozen=True, slots=True)
class RootConfig:
    active_profile: str
    profile: ProfileConfig


class ConfigDecoder:
    """Decode root config data with registered node and attachment kinds."""

    def __init__(
        self,
        *,
        node_kinds: Mapping[str, NodeKindSpec],
        attachment_kinds: Mapping[str, AttachmentKindSpec],
        functions: FunctionRegistry,
    ) -> None:
        self._node_kinds = node_kinds
        self._attachment_kinds = attachment_kinds
        self._functions = functions

    def decode_root(self, data: object) -> RootConfig:
        reader = ConfigReader(data, "config", self._functions)
        active = reader.string("active_profile")
        profiles = dict(reader.items("profiles"))
        reader.finish()
        if active not in profiles:
            raise ConfigError(f"config.active_profile names unknown profile {active!r}")
        profile_reader = ConfigReader(profiles[active], f"config.profiles.{active}", self._functions)
        profile = profile_reader.decode(lambda profile_data: self._decode_profile(active, profile_data))
        return RootConfig(active_profile=active, profile=profile)

    def decode_node(self, reader: ConfigReader) -> NodeConfig:
        return reader.decode(self._decode_node)

    def _decode_profile(self, profile_id: str, reader: ConfigReader) -> ProfileConfig:
        state = reader.data_map("state", {})
        theme_reader = reader.child("theme", None)
        theme = theme_reader.decode(_decode_theme) if theme_reader is not None else ThemeConfig()
        windows = tuple(child.decode(self._decode_window) for child in reader.children("windows"))
        attachments = tuple(
            child.decode(self._decode_attachment) for child in reader.children("attachments", [])
        )
        on: dict[str, tuple[FunctionRef, ...]] = {}
        for event_name, value in reader.items("on", {}):
            functions = value if isinstance(value, (list, tuple)) else (value,)
            refs: list[FunctionRef] = []
            for index, function in enumerate(functions):
                if not callable(function):
                    raise ConfigError(f"{reader.field_path('on')}.{event_name}[{index}] must be a function")
                refs.append(self._functions.register(function))
            on[event_name] = tuple(refs)
        profile = ProfileConfig(
            id=profile_id,
            state=state,
            theme=theme,
            windows=windows,
            attachments=attachments,
            on=on,
        )
        _require_unique((window.id for window in windows), f"{reader.path}.windows")
        _require_unique((node.id for node in profile.nodes()), f"{reader.path} nodes")
        _require_unique((attachment.id for attachment in attachments), f"{reader.path}.attachments")
        return profile

    def _decode_window(self, reader: ConfigReader) -> WindowConfig:
        overlay_reader = reader.child("overlay", None)
        overlay = overlay_reader.decode(_decode_overlay) if overlay_reader is not None else OverlayConfig()
        chrome_reader = reader.child("chrome", None)
        chrome = (
            chrome_reader.decode(lambda chrome_data: ChromeConfig(enabled=chrome_data.boolean("enabled", True)))
            if chrome_reader is not None
            else ChromeConfig()
        )
        content_reader = reader.child("content")
        assert content_reader is not None
        return WindowConfig(
            id=reader.string("id"),
            title=reader.string("title"),
            content=self.decode_node(content_reader),
            style=_decode_style(reader),
            opacity=reader.number("opacity", 1.0, minimum=0.0, maximum=1.0),
            show_on_start=reader.boolean("show_on_start", False),
            overlay=overlay,
            chrome=chrome,
            minimum_size=_size(reader, "minimum_size", (0, 0)),
        )

    def _decode_node(self, reader: ConfigReader) -> NodeConfig:
        kind_name = reader.string("kind")
        kind = self._node_kinds.get(kind_name)
        if kind is None:
            raise ConfigError(f"{reader.field_path('kind')} names unknown node kind {kind_name!r}")
        node_id = reader.string("id")
        bindings: dict[str, Bindable] = {}
        for name, spec in kind.properties.items():
            if not reader.has(name):
                continue
            value = reader.bindable(name)
            if not isinstance(value, FunctionRef) and value is not None and not isinstance(value, spec.value_type):
                raise ConfigError(f"{reader.field_path(name)} has the wrong type for a {kind_name} node")
            bindings[name] = value
        callbacks: dict[str, FunctionRef] = {}
        for field_name, event_name in kind.callbacks.items():
            ref = reader.optional_function(field_name)
            if ref is not None:
                callbacks[event_name] = ref
        children: tuple[NodeConfig, ...] = ()
        if kind.has_children:
            children = tuple(self.decode_node(child) for child in reader.children("children", []))
        cell_reader = reader.child("cell", None)
        return NodeConfig(
            kind=kind_name,
            id=node_id,
            style=_decode_style(reader),
            options=kind.decode_options(reader),
            bindings=bindings,
            callbacks=callbacks,
            children=children,
            cell=cell_reader.decode(_decode_cell) if cell_reader is not None else None,
            stretch=reader.integer("stretch", 0, minimum=0),
        )

    def _decode_attachment(self, reader: ConfigReader) -> AttachmentConfig:
        kind_name = reader.string("kind")
        kind = self._attachment_kinds.get(kind_name)
        if kind is None:
            raise ConfigError(f"{reader.field_path('kind')} names unknown attachment kind {kind_name!r}")
        return AttachmentConfig(kind=kind_name, id=reader.string("id"), options=kind.decode_options(reader))


def _decode_theme(reader: ConfigReader) -> ThemeConfig:
    return ThemeConfig(qss=reader.optional_string("qss") or "")


def _decode_style(reader: ConfigReader) -> StyleConfig:
    style_reader = reader.child("style", None)
    if style_reader is None:
        return StyleConfig()

    def decode(style: ConfigReader) -> StyleConfig:
        return StyleConfig(
            object_name=style.optional_string("object_name"),
            classes=style.string_list("classes", []),
            properties=style.data_map("properties", {}),
            qss=style.optional_string("qss"),
        )

    return style_reader.decode(decode)


def _decode_overlay(reader: ConfigReader) -> OverlayConfig:
    placement = reader.choice(
        "placement",
        frozenset(item.value for item in OverlayPlacement),
        OverlayPlacement.TOP_RIGHT.value,
    )
    return OverlayConfig(
        always_on_top=reader.boolean("always_on_top", True),
        config=AlwaysOnTopWindowConfig(
            placement=OverlayPlacement(placement),
            screen_margin=reader.integer("screen_margin", 16, minimum=0),
            manage_position=reader.boolean("manage_position", True),
        ),
    )


def _decode_cell(reader: ConfigReader) -> GridCell:
    return GridCell(
        row=reader.integer("row", minimum=0),
        column=reader.integer("column", minimum=0),
        row_span=reader.integer("row_span", 1, minimum=1),
        column_span=reader.integer("column_span", 1, minimum=1),
    )


def _size(reader: ConfigReader, key: str, default: tuple[int, int]) -> tuple[int, int]:
    value = reader.raw(key, list(default))
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in value)
    ):
        raise ConfigError(f"{reader.field_path(key)} must be [width, height] in pixels")
    return (value[0], value[1])


def _require_unique(ids: Iterable[str], scope: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in ids:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    if duplicates:
        raise ConfigError(f"Duplicate IDs in {scope}: {', '.join(sorted(duplicates))}")
