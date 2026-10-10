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

Node kinds and attachment kinds register how their options decode, and a
node kind with children also decodes the placement fields its children carry,
such as a grid ``cell``. The decoder here owns everything common to every
kind: IDs, style, bindings, callbacks, and children.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from ..function_registry import FunctionRef, FunctionRegistry
from ..messages import DataMap, DataValue
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

    @property
    def widget_properties(self) -> frozenset[str]:
        """Widget properties the kind sets itself, which a profile style cannot set."""
        ...

    def decode_options(self, reader: ConfigReader, /) -> object: ...

    def decode_child_placement(self, reader: ConfigReader, /) -> object:
        """Read the fields this kind places its children with, such as a grid ``cell``."""
        ...


PlacementDecoder = Callable[[ConfigReader], object]


class AttachmentKindSpec(Protocol):
    def decode_options(self, reader: ConfigReader, /) -> object: ...


ENGINE_WIDGET_PROPERTIES = frozenset({"componentType", "componentId", "classes", "pointerLocatorEnabled"})
"""Widget properties the engine sets on windows and nodes, which a profile style cannot set."""


@dataclass(frozen=True, slots=True)
class StyleConfig:
    object_name: str | None = None
    classes: tuple[str, ...] = ()
    properties: DataMap = field(default_factory=dict)
    qss: str | None = None


@dataclass(frozen=True, slots=True)
class NodeConfig:
    """One decoded node.

    Kind-specific settings live in ``options``. ``placement`` holds what the
    parent kind decoded for this child, such as a grid cell; it is ``None``
    for a window's content.
    """

    kind: str
    id: str
    style: StyleConfig
    options: object
    bindings: Mapping[str, Bindable]
    callbacks: Mapping[str, FunctionRef]
    children: tuple["NodeConfig", ...] = ()
    placement: object = None

    def walk(self) -> "list[NodeConfig]":
        nodes: list[NodeConfig] = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes


@dataclass(frozen=True, slots=True)
class WindowConfig:
    """One decoded window; ``_decode_window`` owns every default.

    ``default_close`` keeps the engine's close rule for this window: closing it
    closes it, and closing the last visible window asks to quit. A profile
    turns it off for a window whose close it handles itself.
    """

    id: str
    title: str
    content: NodeConfig
    style: StyleConfig
    opacity: float
    show_on_start: bool
    overlay: OverlayConfig
    chrome: ChromeConfig
    minimum_size: tuple[int, int]
    default_close: bool


@dataclass(frozen=True, slots=True)
class AttachmentConfig:
    kind: str
    id: str
    options: object


PALETTE_ROLES = frozenset(
    {
        "window",
        "base",
        "alternate_base",
        "window_text",
        "text",
        "button",
        "button_text",
        "highlight",
        "highlighted_text",
        "placeholder_text",
    }
)
"""Qt palette roles a theme may color, named the way Lua configs spell them."""

FONT_WEIGHTS = frozenset(
    {"thin", "extra_light", "light", "normal", "medium", "demi_bold", "bold", "extra_bold", "black"}
)


@dataclass(frozen=True, slots=True)
class FontConfig:
    families: tuple[str, ...]
    pixel_size: int
    weight: str


@dataclass(frozen=True, slots=True)
class ThemeConfig:
    """A profile's look: Qt palette colors by role, the application font, and its stylesheet."""

    qss: str = ""
    palette: Mapping[str, str] = field(default_factory=dict)
    font: FontConfig | None = None


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


ProfileCheck = Callable[[ProfileConfig, str], None]
"""Engine checks a decoded profile must pass, given the profile and its config path."""


class ConfigDecoder:
    """Decode root config data with registered node and attachment kinds."""

    def __init__(
        self,
        *,
        node_kinds: Mapping[str, NodeKindSpec],
        attachment_kinds: Mapping[str, AttachmentKindSpec],
        functions: FunctionRegistry,
        check_profile: ProfileCheck,
    ) -> None:
        self._node_kinds = node_kinds
        self._attachment_kinds = attachment_kinds
        self._functions = functions
        self._check_profile = check_profile

    def decode_root(self, data: object) -> ProfileConfig:
        """Validate every profile in a root config and return the active one."""

        reader = ConfigReader(data, "config", self._functions)
        active = reader.string("active_profile")
        profiles = reader.items("profiles")
        reader.finish()
        decoded: dict[str, ProfileConfig] = {}
        for name, value in profiles:
            profile_reader = ConfigReader(value, _profile_path(name), self._functions)
            decoded[name] = profile_reader.decode(lambda profile_data, name=name: self._decode_profile(name, profile_data))
        if active not in decoded:
            raise ConfigError(f"config.active_profile names unknown profile {active!r}")
        return decoded[active]

    def decode_node(self, reader: ConfigReader, placement: PlacementDecoder | None = None) -> NodeConfig:
        """Decode one node; ``placement`` reads the fields its parent kind places it with."""

        return reader.decode(lambda node: self._decode_node(node, placement))

    def _decode_profile(self, profile_id: str, reader: ConfigReader) -> ProfileConfig:
        state = reader.data_map("state", {})
        theme_reader = reader.optional_child("theme")
        theme = theme_reader.decode(_decode_theme) if theme_reader is not None else ThemeConfig()
        windows = tuple(child.decode(self._decode_window) for child in reader.children("windows"))
        attachments = tuple(
            child.decode(self._decode_attachment) for child in reader.children("attachments", [])
        )
        on: dict[str, tuple[FunctionRef, ...]] = {}
        for event_name, value in reader.items("on", {}):
            functions = value if isinstance(value, list) else [value]
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
        self._check_profile(profile, reader.path)
        return profile

    def _decode_window(self, reader: ConfigReader) -> WindowConfig:
        overlay_reader = reader.optional_child("overlay")
        overlay = overlay_reader.decode(_decode_overlay) if overlay_reader is not None else OverlayConfig()
        chrome_reader = reader.optional_child("chrome")
        chrome = chrome_reader.decode(_decode_chrome) if chrome_reader is not None else ChromeConfig()
        return WindowConfig(
            id=reader.string("id"),
            title=reader.string("title"),
            content=self.decode_node(reader.child("content")),
            style=_decode_style(reader),
            opacity=reader.number("opacity", 1.0, minimum=0.0, maximum=1.0),
            show_on_start=reader.boolean("show_on_start", False),
            overlay=overlay,
            chrome=chrome,
            minimum_size=_pair(reader.integer_list("minimum_size", (0, 0), shape="[width, height] in pixels")),
            default_close=reader.boolean("default_close", True),
        )

    def _decode_node(self, reader: ConfigReader, placement: PlacementDecoder | None) -> NodeConfig:
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
            if not isinstance(value, FunctionRef) and not isinstance(value, spec.value_type):
                raise ConfigError(f"{reader.field_path(name)} has the wrong type for a {kind_name} node")
            bindings[name] = value
        callbacks: dict[str, FunctionRef] = {}
        for field_name, event_name in kind.callbacks.items():
            ref = reader.optional_function(field_name)
            if ref is not None:
                callbacks[event_name] = ref
        children: tuple[NodeConfig, ...] = ()
        if kind.has_children:
            children = tuple(
                self.decode_node(child, kind.decode_child_placement) for child in reader.children("children", [])
            )
        return NodeConfig(
            kind=kind_name,
            id=node_id,
            style=_decode_style(reader, ENGINE_WIDGET_PROPERTIES | kind.widget_properties),
            options=kind.decode_options(reader),
            bindings=bindings,
            callbacks=callbacks,
            children=children,
            placement=placement(reader) if placement is not None else None,
        )

    def _decode_attachment(self, reader: ConfigReader) -> AttachmentConfig:
        kind_name = reader.string("kind")
        kind = self._attachment_kinds.get(kind_name)
        if kind is None:
            raise ConfigError(f"{reader.field_path('kind')} names unknown attachment kind {kind_name!r}")
        return AttachmentConfig(kind=kind_name, id=reader.string("id"), options=kind.decode_options(reader))


def _decode_theme(reader: ConfigReader) -> ThemeConfig:
    palette_reader = reader.optional_child("palette")
    palette = palette_reader.decode(_decode_palette) if palette_reader is not None else {}
    font_reader = reader.optional_child("font")
    font = font_reader.decode(_decode_font) if font_reader is not None else None
    return ThemeConfig(qss=reader.optional_string("qss") or "", palette=palette, font=font)


def _decode_palette(reader: ConfigReader) -> dict[str, str]:
    """Read colors by palette role; ``finish`` rejects a role name Qt does not have."""

    return {role: reader.color(role) for role in sorted(PALETTE_ROLES) if reader.has(role)}


def _decode_font(reader: ConfigReader) -> FontConfig:
    return FontConfig(
        families=reader.string_list("families"),
        pixel_size=reader.integer("pixel_size", minimum=1),
        weight=reader.choice("weight", FONT_WEIGHTS, "normal"),
    )


def _decode_style(reader: ConfigReader, reserved: frozenset[str] = ENGINE_WIDGET_PROPERTIES) -> StyleConfig:
    style_reader = reader.optional_child("style")
    if style_reader is None:
        return StyleConfig()

    def decode(style: ConfigReader) -> StyleConfig:
        properties = style.data_map("properties", {})
        taken = sorted(name for name in properties if name in reserved)
        if taken:
            raise ConfigError(f"{style.field_path('properties')} cannot set engine properties: {', '.join(taken)}")
        return StyleConfig(
            object_name=style.optional_string("object_name"),
            classes=style.string_list("classes", []),
            properties=properties,
            qss=style.optional_string("qss"),
        )

    return style_reader.decode(decode)


def _decode_overlay(reader: ConfigReader) -> OverlayConfig:
    defaults = OverlayConfig()
    placement = reader.choice(
        "placement",
        frozenset(item.value for item in OverlayPlacement),
        defaults.config.placement.value,
    )
    return OverlayConfig(
        always_on_top=reader.boolean("always_on_top", defaults.always_on_top),
        config=AlwaysOnTopWindowConfig(
            placement=OverlayPlacement(placement),
            screen_margin=reader.integer("screen_margin", defaults.config.screen_margin, minimum=0),
            manage_position=reader.boolean("manage_position", defaults.config.manage_position),
        ),
    )


def _decode_chrome(reader: ConfigReader) -> ChromeConfig:
    return ChromeConfig(enabled=reader.boolean("enabled", ChromeConfig().enabled))


def _profile_path(name: str) -> str:
    """Config path of one profile; a name containing dots is quoted so the path stays readable."""

    return f"config.profiles[{name!r}]" if "." in name else f"config.profiles.{name}"


def _pair(values: tuple[int, ...]) -> tuple[int, int]:
    return (values[0], values[1])


def _require_unique(ids: Iterable[str], scope: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in ids:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    if duplicates:
        raise ConfigError(f"Duplicate IDs in {scope}: {', '.join(sorted(duplicates))}")
