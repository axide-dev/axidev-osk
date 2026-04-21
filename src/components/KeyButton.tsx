import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type CSSProperties,
  type ForwardedRef,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import type { KeySpec } from '../layout/usIsoLayout';
import type {
  KeyButtonConfig,
  KeyButtonDisplay,
  KeyButtonOptions,
} from './keyButton.types';

export type { KeyButtonConfig, KeyButtonDisplay, KeyButtonOptions } from './keyButton.types';

export type KeyButtonVisualState = 'idle' | 'hovered' | 'pressed';

export type KeyButtonSnapshot = {
  keyId: string;
  label: string;
  subLabel?: string;
  legend?: string;
  a11yLabel?: string;
  state: KeyButtonVisualState;
  latched: boolean;
};

export type KeyButtonEvent = KeyButtonSnapshot & {
  source: 'pointer' | 'prop' | 'api';
};

export type KeyButtonHandle = {
  hover: () => void;
  idle: () => void;
  pressIn: () => void;
  pressOut: () => void;
  resetState: () => void;
  setDisplay: (display: KeyButtonDisplay) => void;
  resetDisplay: () => void;
  setLatched: (latched: boolean) => void;
  toggleLatched: () => void;
  getSnapshot: () => KeyButtonSnapshot;
};

type KeyButtonProps = {
  keySpec: KeySpec;
  display?: KeyButtonDisplay;
  options?: KeyButtonOptions;
  config?: KeyButtonConfig;
  disabled?: boolean;
  pressed?: boolean;
  latched?: boolean;
  onTap?: (event: KeyButtonEvent) => void;
  onHold?: (event: KeyButtonEvent) => void;
  onPressIn?: (event: KeyButtonEvent) => void;
  onPressOut?: (event: KeyButtonEvent) => void;
  onHoverStart?: (event: KeyButtonEvent) => void;
  onHoverEnd?: (event: KeyButtonEvent) => void;
  onStateChange?: (event: KeyButtonEvent) => void;
  onLatchChange?: (event: KeyButtonEvent) => void;
  onLatchIn?: (event: KeyButtonEvent) => void;
  onLatchOut?: (event: KeyButtonEvent) => void;
};

const defaultOptions: Required<KeyButtonOptions> = {
  holdDelayMs: 400,
  sticky: false,
  stickyMode: 'toggle',
  defaultLatched: false,
};

function KeyButton(
  {
    keySpec,
    display,
    options,
    config,
    disabled = false,
    pressed = false,
    latched,
    onTap,
    onHold,
    onPressIn,
    onPressOut,
    onHoverStart,
    onHoverEnd,
    onStateChange,
    onLatchChange,
    onLatchIn,
    onLatchOut,
  }: KeyButtonProps,
  ref: ForwardedRef<KeyButtonHandle>,
) {
  const resolvedOptions = {
    ...defaultOptions,
    ...keySpec.button?.options,
    ...config?.options,
    ...options,
  };
  const holdTimerRef = useRef<number | null>(null);
  const holdTriggeredRef = useRef(false);
  const hoveredRef = useRef(false);
  const pointerPressedRef = useRef(false);
  const pressedRef = useRef(pressed);
  const [internalLatched, setInternalLatched] = useState(
    resolvedOptions.defaultLatched,
  );
  const [displayOverride, setDisplayOverride] = useState<KeyButtonDisplay>({});
  const [visualState, setVisualState] = useState<KeyButtonVisualState>('idle');
  const previousStateRef = useRef<KeyButtonVisualState>('idle');
  const previousLatchedRef = useRef(Boolean(latched ?? resolvedOptions.defaultLatched));
  const stateChangeSourceRef = useRef<KeyButtonEvent['source']>('prop');
  const latchChangeSourceRef = useRef<KeyButtonEvent['source']>('prop');

  const effectiveDisplay = {
    label: keySpec.label,
    subLabel: keySpec.subLabel,
    legend: keySpec.legend,
    a11yLabel: keySpec.a11yLabel,
    ...keySpec.button?.display,
    ...config?.display,
    ...display,
    ...displayOverride,
  };
  const effectiveLatched = latched ?? internalLatched;

  const style: CSSProperties = {
    gridColumn: `${keySpec.column} / span ${keySpec.width}`,
    gridRow: `${keySpec.row} / span ${keySpec.height ?? 1}`,
  };

  const buildSnapshot = (
    nextState = visualState,
    nextLatched = effectiveLatched,
  ): KeyButtonSnapshot => ({
    keyId: keySpec.id,
    label: effectiveDisplay.label,
    subLabel: effectiveDisplay.subLabel,
    legend: effectiveDisplay.legend,
    a11yLabel: effectiveDisplay.a11yLabel,
    state: nextState,
    latched: nextLatched,
  });

  const buildEvent = (
    source: KeyButtonEvent['source'],
    nextState = visualState,
    nextLatched = effectiveLatched,
  ): KeyButtonEvent => ({
    ...buildSnapshot(nextState, nextLatched),
    source,
  });

  const resolveVisualState = (
    pointerPressed: boolean,
    hovered: boolean,
    forcedPressed: boolean,
  ): KeyButtonVisualState => {
    if (forcedPressed || pointerPressed) {
      return 'pressed';
    }

    if (hovered) {
      return 'hovered';
    }

    return 'idle';
  };

  const syncVisualState = (latchedOverride = effectiveLatched) => {
    const nextState = resolveVisualState(
      pointerPressedRef.current,
      hoveredRef.current,
      pressedRef.current || latchedOverride,
    );

    setVisualState((currentState) =>
      currentState === nextState ? currentState : nextState,
    );

    return nextState;
  };

  const clearHoldTimer = () => {
    if (holdTimerRef.current !== null) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
  };

  const setLatchedState = (
    nextLatched: boolean,
    source: KeyButtonEvent['source'],
  ) => {
    latchChangeSourceRef.current = source;

    if (latched === undefined) {
      setInternalLatched(nextLatched);
    }
  };

  const clearPointerPress = () => {
    clearHoldTimer();
    pointerPressedRef.current = false;
    holdTriggeredRef.current = false;
    return syncVisualState();
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    clearHoldTimer();
    holdTriggeredRef.current = false;
    pointerPressedRef.current = true;
    hoveredRef.current = true;
    stateChangeSourceRef.current = 'pointer';
    syncVisualState();
    event.currentTarget.setPointerCapture(event.pointerId);

    onPressIn?.(
      buildEvent(
        'pointer',
        resolveVisualState(true, true, pressedRef.current || effectiveLatched),
      ),
    );

    holdTimerRef.current = window.setTimeout(() => {
      holdTriggeredRef.current = true;
      onHold?.(buildEvent('pointer'));
    }, resolvedOptions.holdDelayMs);
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const wasHold = holdTriggeredRef.current;

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    if (!wasHold) {
      let nextLatched = effectiveLatched;

      if (resolvedOptions.sticky && resolvedOptions.stickyMode === 'toggle') {
        nextLatched = !effectiveLatched;
        setLatchedState(nextLatched, 'pointer');
      }

      pointerPressedRef.current = false;
      holdTriggeredRef.current = false;
      clearHoldTimer();
      stateChangeSourceRef.current = 'pointer';
      const nextState = syncVisualState(nextLatched);

      onPressOut?.(buildEvent('pointer', nextState, nextLatched));
      onTap?.(
        buildEvent(
          'pointer',
          nextState,
          nextLatched,
        ),
      );

      return;
    }

    const nextState = clearPointerPress();
    onPressOut?.(buildEvent('pointer', nextState));
  };

  const handlePointerCancel = () => {
    stateChangeSourceRef.current = 'pointer';
    const nextState = clearPointerPress();
    onPressOut?.(buildEvent('pointer', nextState));
  };

  const handlePointerEnter = () => {
    hoveredRef.current = true;
    stateChangeSourceRef.current = 'pointer';
    const nextState = syncVisualState();
    onHoverStart?.(buildEvent('pointer', nextState));
  };

  const handlePointerLeave = () => {
    hoveredRef.current = false;
    stateChangeSourceRef.current = 'pointer';
    const nextState = syncVisualState();
    onHoverEnd?.(buildEvent('pointer', nextState));
  };

  useImperativeHandle(ref, () => ({
    hover: () => {
      hoveredRef.current = true;
      stateChangeSourceRef.current = 'api';
      syncVisualState();
    },
    idle: () => {
      hoveredRef.current = false;
      pointerPressedRef.current = false;
      clearHoldTimer();
      holdTriggeredRef.current = false;
      stateChangeSourceRef.current = 'api';
      syncVisualState();
    },
    pressIn: () => {
      clearHoldTimer();
      holdTriggeredRef.current = false;
      pointerPressedRef.current = false;
      setLatchedState(true, 'api');
      stateChangeSourceRef.current = 'api';
      syncVisualState(true);
    },
    pressOut: () => {
      clearHoldTimer();
      holdTriggeredRef.current = false;
      pointerPressedRef.current = false;
      setLatchedState(false, 'api');
      stateChangeSourceRef.current = 'api';
      syncVisualState(false);
    },
    resetState: () => {
      hoveredRef.current = false;
      pointerPressedRef.current = false;
      clearHoldTimer();
      holdTriggeredRef.current = false;
      setLatchedState(false, 'api');
      stateChangeSourceRef.current = 'api';
      syncVisualState(false);
    },
    setDisplay: (nextDisplay) => {
      setDisplayOverride((currentDisplay) => ({
        ...currentDisplay,
        ...nextDisplay,
      }));
    },
    resetDisplay: () => {
      setDisplayOverride({});
    },
    setLatched: (nextLatched) => {
      setLatchedState(nextLatched, 'api');
      stateChangeSourceRef.current = 'api';
      syncVisualState(nextLatched);
    },
    toggleLatched: () => {
      setLatchedState(!effectiveLatched, 'api');
      stateChangeSourceRef.current = 'api';
      syncVisualState(!effectiveLatched);
    },
    getSnapshot: () => buildSnapshot(),
  }));

  useEffect(() => {
    pressedRef.current = pressed;
    stateChangeSourceRef.current = 'prop';
    syncVisualState();
  }, [pressed, effectiveLatched]);

  useEffect(() => {
    const previousState = previousStateRef.current;

    if (previousState === visualState) {
      return;
    }

    previousStateRef.current = visualState;
    onStateChange?.(buildEvent(stateChangeSourceRef.current));
    stateChangeSourceRef.current = 'prop';
  }, [onStateChange, visualState]);

  useEffect(() => {
    const previousLatched = previousLatchedRef.current;

    if (previousLatched === effectiveLatched) {
      return;
    }

    previousLatchedRef.current = effectiveLatched;
    onLatchChange?.(buildEvent(latchChangeSourceRef.current));

    if (effectiveLatched) {
      onLatchIn?.(buildEvent(latchChangeSourceRef.current));
      latchChangeSourceRef.current = 'prop';
      return;
    }

    onLatchOut?.(buildEvent(latchChangeSourceRef.current));
    latchChangeSourceRef.current = 'prop';
  }, [effectiveLatched, onLatchChange, onLatchIn, onLatchOut, visualState]);

  useEffect(() => {
    return () => {
      clearHoldTimer();
    };
  }, []);

  return (
    <button
      type="button"
      className="key-button"
      style={style}
      disabled={disabled}
      data-state={visualState}
      data-latched={effectiveLatched}
      data-disabled={disabled}
      data-tone={config?.tone ?? keySpec.button?.tone ?? 'default'}
      data-shape={config?.shape ?? keySpec.button?.shape ?? 'default'}
      aria-label={effectiveDisplay.a11yLabel ?? effectiveDisplay.label}
      aria-pressed={visualState === 'pressed'}
      tabIndex={-1}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
      onMouseDown={(event) => {
        event.preventDefault();
      }}
      onFocus={(event) => {
        event.currentTarget.blur();
      }}
      onLostPointerCapture={handlePointerCancel}
      onContextMenu={(event) => event.preventDefault()}
    >
      <span className="key-stack">
        <span className="key-label">{effectiveDisplay.label}</span>
        {effectiveDisplay.subLabel ? (
          <span className="key-meta">{effectiveDisplay.subLabel}</span>
        ) : null}
      </span>
      {effectiveDisplay.legend ? (
        <span className="key-meta">{effectiveDisplay.legend}</span>
      ) : null}
    </button>
  );
}

export default forwardRef(KeyButton);
