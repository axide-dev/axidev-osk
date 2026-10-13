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
from typing import Generic, Protocol, TypeVar

from ..function_registry import FunctionRef, FunctionRegistry
from ..messages import DataMap
from ..widget_properties import ENGINE_WIDGET_PROPERTIES
from .models import AlwaysOnTopWindowConfig, ChromeConfig, OverlayConfig, OverlayPlacement
from .reader import ConfigError, ConfigReader, Resolver
from .variables import StatePath, Variable, VariableError, decode_state

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Live(Generic[T]):
    """Values that may follow state: what they decoded to at load, and how to decode them again.

    ``initial`` comes from the profile's default state. ``decode`` re-reads the
    same config map through a resolver over current state; it raises when a
    binding fails or its result is invalid, so the caller keeps its last value.
    """

    initial: T
    decode: Callable[[Resolver], T]


class NodeKindSpec(Protocol):
    """What the profile decoder needs to know about one node kind."""

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

    def decode_structure(self, reader: ConfigReader, /) -> object:
        """Read the kind's fixed fields, such as a box's ``direction``."""
        ...

    def decode_options(self, reader: ConfigReader, /) -> object:
        """Read the kind's values; any of them may be a binding."""
        ...

    def decode_child_placement(self, reader: ConfigReader, /) -> object:
        """Read the fields this kind places its children with, such as a grid ``cell``."""
        ...

    def check_options(self, reader: ConfigReader, options: object, children: tuple[str, ...], /) -> None:
        """Reject options that do not fit the node's children, given their IDs."""
        ...


PlacementDecoder = Callable[[ConfigReader], object]


class AttachmentKindSpec(Protocol):
    @property
    def limit(self) -> str | None:
        """``"window"`` or ``"profile"`` when at most one attachment of the kind fits there."""
        ...

    def decode_target(self, reader: ConfigReader, /) -> str | None:
        """Read the fixed window the attachment acts on, or ``None`` for a screen-wide one."""
        ...

    def decode_options(self, reader: ConfigReader, /) -> object: ...


@dataclass(frozen=True, slots=True)
class StyleConfig:
    object_name: str | None = None
    classes: tuple[str, ...] = ()
    properties: DataMap = field(default_factory=dict)
    qss: str | None = None


@dataclass(frozen=True, slots=True)
class NodeValues:
    """A node's values: its kind's options and its style hooks."""

    options: object
    style: StyleConfig


@dataclass(frozen=True, slots=True)
class NodeConfig:
    """One decoded node.

    ``values`` holds everything that may follow state. ``structure`` holds the
    kind's fixed fields. ``placement`` holds what the parent kind decoded for
    this child, such as a grid cell; it is ``None`` for a window's content.
    ``passes_input_block`` lets the node take clicks while its window blocks input.
    """

    kind: str
    id: str
    values: Live[NodeValues]
    callbacks: Mapping[str, FunctionRef]
    children: tuple["NodeConfig", ...] = ()
    structure: object = None
    placement: object = None
    passes_input_block: bool = False

    def walk(self) -> "list[NodeConfig]":
        nodes: list[NodeConfig] = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes


@dataclass(frozen=True, slots=True)
class WindowValues:
    """A window's values, any of which may follow state.

    ``default_close`` keeps the engine's close rule for this window: closing it
    closes it, and closing the last visible window asks to quit. A profile
    turns it off for a window whose close it handles itself.
    ``input_blocked`` ignores clicks except on nodes with ``passes_input_block``.
    """

    title: str
    opacity: float
    minimum_size: tuple[int, int]
    default_close: bool
    input_blocked: bool
    style: StyleConfig


@dataclass(frozen=True, slots=True)
class WindowConfig:
    """One decoded window: fixed identity, platform surface, and content, plus its values."""

    id: str
    content: NodeConfig
    show_on_start: bool
    overlay: OverlayConfig
    chrome: ChromeConfig
    values: Live[WindowValues]


@dataclass(frozen=True, slots=True)
class AttachmentConfig:
    kind: str
    id: str
    target: str | None
    values: Live[object]


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
    """One decoded profile.

    ``state`` holds the profile's own variable declarations, which reset when
    it starts. ``shared`` holds the root config's declarations, which every
    profile shares and which survive a profile switch.
    """

    id: str
    state: Mapping[StatePath, Variable]
    shared: Mapping[StatePath, Variable]
    theme: Live[ThemeConfig]
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

LoadState = Callable[[Mapping[StatePath, Variable], Mapping[StatePath, Variable]], Resolver]
"""Build a resolver over default state for a profile's shared and own declarations, raising on overlaps."""


class ConfigDecoder:
    """Decode root config data with registered node and attachment kinds."""

    def __init__(
        self,
        *,
        node_kinds: Mapping[str, NodeKindSpec],
        attachment_kinds: Mapping[str, AttachmentKindSpec],
        functions: FunctionRegistry,
        check_profile: ProfileCheck,
        load_state: LoadState,
    ) -> None:
        self._node_kinds = node_kinds
        self._attachment_kinds = attachment_kinds
        self._functions = functions
        self._check_profile = check_profile
        self._load_state = load_state

    def decode_root(self, data: object) -> ProfileConfig:
        """Validate every profile in a root config and return the active one."""

        reader = ConfigReader(data, "config", self._functions)
        active = reader.string("active_profile")
        profiles = reader.items("profiles")
        shared = _declarations(reader.raw("state", {}), "config.state")
        reader.finish()
        decoded: dict[str, ProfileConfig] = {}
        for name, value in profiles:
            profile_reader = ConfigReader(value, _profile_path(name), self._functions)
            decoded[name] = profile_reader.decode(
                lambda profile_data, name=name: self._decode_profile(name, profile_data, shared)
            )
        if active not in decoded:
            raise ConfigError(f"config.active_profile names unknown profile {active!r}")
        return decoded[active]

    def _decode_profile(
        self,
        profile_id: str,
        reader: ConfigReader,
        shared: Mapping[StatePath, Variable],
    ) -> ProfileConfig:
        state = _declarations(reader.raw("state", {}), reader.field_path("state"))
        try:
            resolver = self._load_state(shared, state)
        except VariableError as exc:
            raise ConfigError(f"{reader.field_path('state')}: {exc}") from exc
        theme_reader = reader.optional_child("theme")
        if theme_reader is not None:
            theme = _live(theme_reader, resolver, _decode_theme)
            theme_reader.finish()
        else:
            theme = Live(ThemeConfig(), lambda _resolver: ThemeConfig())
        windows = tuple(child.decode(lambda window: self._decode_window(window, resolver)) for child in reader.children("windows"))
        attachments = tuple(
            child.decode(lambda attachment: self._decode_attachment(attachment, resolver))
            for child in reader.children("attachments", [])
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
            shared=shared,
            theme=theme,
            windows=windows,
            attachments=attachments,
            on=on,
        )
        _require_unique((window.id for window in windows), f"{reader.path}.windows")
        _require_unique((node.id for node in profile.nodes()), f"{reader.path} nodes")
        _require_unique((attachment.id for attachment in attachments), f"{reader.path}.attachments")
        self._check_attachments(attachments, {window.id for window in windows}, reader.field_path("attachments"))
        self._check_profile(profile, reader.path)
        return profile

    def _check_attachments(self, attachments: tuple[AttachmentConfig, ...], windows: set[str], path: str) -> None:
        """Reject an attachment naming an unknown window, or more of a kind than its limit allows."""

        seen: set[tuple[str, str | None]] = set()
        for index, attachment in enumerate(attachments):
            if attachment.target is not None and attachment.target not in windows:
                raise ConfigError(f"{path}[{index}] targets unknown window {attachment.target!r}")
            limit = self._attachment_kinds[attachment.kind].limit
            if limit is None:
                continue
            key = (attachment.kind, attachment.target if limit == "window" else None)
            if key in seen:
                where = f"window {attachment.target!r}" if limit == "window" else "a profile"
                raise ConfigError(f"{path}[{index}]: {where} can have at most one {attachment.kind} attachment")
            seen.add(key)

    def _decode_window(self, reader: ConfigReader, resolver: Resolver) -> WindowConfig:
        overlay_reader = reader.optional_child("overlay")
        overlay = overlay_reader.decode(_decode_overlay) if overlay_reader is not None else OverlayConfig()
        chrome_reader = reader.optional_child("chrome")
        chrome = chrome_reader.decode(_decode_chrome) if chrome_reader is not None else ChromeConfig()
        return WindowConfig(
            id=reader.string("id"),
            content=self._decode_node(reader.child("content"), None, resolver),
            show_on_start=reader.boolean("show_on_start", False),
            overlay=overlay,
            chrome=chrome,
            values=_live(reader, resolver, _decode_window_values),
        )

    def _decode_node(self, reader: ConfigReader, placement: PlacementDecoder | None, resolver: Resolver) -> NodeConfig:
        return reader.decode(lambda node: self._decode_node_fields(node, placement, resolver))

    def _decode_node_fields(
        self,
        reader: ConfigReader,
        placement: PlacementDecoder | None,
        resolver: Resolver,
    ) -> NodeConfig:
        kind_name = reader.string("kind")
        kind = self._node_kinds.get(kind_name)
        if kind is None:
            raise ConfigError(f"{reader.field_path('kind')} names unknown node kind {kind_name!r}")
        node_id = reader.string("id")
        callbacks: dict[str, FunctionRef] = {}
        for field_name, event_name in kind.callbacks.items():
            ref = reader.optional_function(field_name)
            if ref is not None:
                callbacks[event_name] = ref
        children: tuple[NodeConfig, ...] = ()
        if kind.has_children:
            children = tuple(
                self._decode_node(child, kind.decode_child_placement, resolver)
                for child in reader.children("children", [])
            )
        reserved = ENGINE_WIDGET_PROPERTIES | kind.widget_properties
        structure = kind.decode_structure(reader)
        # The parent reads its placement fields first, so it can reject a field before a binding in it runs.
        child_placement = placement(reader) if placement is not None else None
        child_ids = tuple(child.id for child in children)

        def decode_values(values: ConfigReader) -> NodeValues:
            options = kind.decode_options(values)
            kind.check_options(values, options, child_ids)
            return NodeValues(options=options, style=_decode_style(values, reserved))

        return NodeConfig(
            kind=kind_name,
            id=node_id,
            values=_live(reader, resolver, decode_values),
            callbacks=callbacks,
            children=children,
            structure=structure,
            placement=child_placement,
            passes_input_block=reader.boolean("passes_input_block", False),
        )

    def _decode_attachment(self, reader: ConfigReader, resolver: Resolver) -> AttachmentConfig:
        kind_name = reader.string("kind")
        kind = self._attachment_kinds.get(kind_name)
        if kind is None:
            raise ConfigError(f"{reader.field_path('kind')} names unknown attachment kind {kind_name!r}")
        return AttachmentConfig(
            kind=kind_name,
            id=reader.string("id"),
            target=kind.decode_target(reader),
            values=_live(reader, resolver, kind.decode_options),
        )


def _live(reader: ConfigReader, resolver: Resolver, decode: Callable[[ConfigReader], T]) -> Live[T]:
    """Decode values once from default state and keep how to decode them again."""

    return Live(initial=decode(reader.live(resolver)), decode=lambda current: decode(reader.fresh(current)))


def _declarations(data: object, path: str) -> dict[StatePath, Variable]:
    try:
        return decode_state(data, path)
    except VariableError as exc:
        raise ConfigError(str(exc)) from exc


def _decode_window_values(reader: ConfigReader) -> WindowValues:
    return WindowValues(
        title=reader.string("title"),
        opacity=reader.number("opacity", 1.0, minimum=0.0, maximum=1.0),
        minimum_size=_pair(reader.integer_list("minimum_size", (0, 0), shape="[width, height] in pixels")),
        default_close=reader.boolean("default_close", True),
        input_blocked=reader.boolean("input_blocked", False),
        style=_decode_style(reader),
    )


def _decode_theme(reader: ConfigReader) -> ThemeConfig:
    palette_reader = reader.optional_child("palette")
    palette = palette_reader.decode(_decode_palette) if palette_reader is not None else {}
    font_reader = reader.optional_child("font")
    font = font_reader.decode(_decode_font) if font_reader is not None else None
    return ThemeConfig(qss=reader.optional_string("qss") or "", palette=palette, font=font)


def _decode_palette(reader: ConfigReader) -> dict[str, str]:
    """Read colors by palette role; ``finish`` rejects a role name Qt does not have."""

    colors = {role: reader.optional_color(role) for role in sorted(PALETTE_ROLES)}
    return {role: color for role, color in colors.items() if color is not None}


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
