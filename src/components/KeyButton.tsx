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

export type KeyButtonVisualState = 'idle' | 'hovered' | 'pressed';

export type KeyButtonDisplay = Partial<
  Pick<KeySpec, 'label' | 'subLabel' | 'legend' | 'a11yLabel'>
>;

export type KeyButtonHandle = {
  hover: () => void;
  idle: () => void;
  pressIn: () => void;
  pressOut: () => void;
  resetState: () => void;
  setDisplay: (display: KeyButtonDisplay) => void;
  resetDisplay: () => void;
};

type KeyButtonProps = {
  keySpec: KeySpec;
  display?: KeyButtonDisplay;
  pressed?: boolean;
  onTap?: (keyId: string) => void;
  onHold?: (keyId: string) => void;
  onStateChange?: (keyId: string, state: KeyButtonVisualState) => void;
};

const HOLD_DELAY_MS = 400;

function KeyButton(
  { keySpec, display, pressed = false, onTap, onHold, onStateChange }: KeyButtonProps,
  ref: ForwardedRef<KeyButtonHandle>,
) {
  const holdTimerRef = useRef<number | null>(null);
  const holdTriggeredRef = useRef(false);
  const hoveredRef = useRef(false);
  const pointerPressedRef = useRef(false);
  const pressedRef = useRef(pressed);
  const latchedPressedRef = useRef(false);
  const [latchedPressed, setLatchedPressed] = useState(false);
  const [displayOverride, setDisplayOverride] = useState<KeyButtonDisplay>({});
  const [visualState, setVisualState] = useState<KeyButtonVisualState>('idle');

  const style: CSSProperties = {
    gridColumn: `${keySpec.column} / span ${keySpec.width}`,
    gridRow: `${keySpec.row} / span ${keySpec.height ?? 1}`,
  };

  const effectiveDisplay = {
    label: keySpec.label,
    subLabel: keySpec.subLabel,
    legend: keySpec.legend,
    a11yLabel: keySpec.a11yLabel,
    ...display,
    ...displayOverride,
  };

  const syncVisualState = () => {
    const nextState: KeyButtonVisualState =
      pressedRef.current || latchedPressedRef.current || pointerPressedRef.current
        ? 'pressed'
        : hoveredRef.current
          ? 'hovered'
          : 'idle';

    setVisualState((currentState) =>
      currentState === nextState ? currentState : nextState,
    );
  };

  const clearHoldTimer = () => {
    if (holdTimerRef.current !== null) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
  };

  const clearPointerPress = () => {
    clearHoldTimer();
    pointerPressedRef.current = false;
    holdTriggeredRef.current = false;
    syncVisualState();
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    clearHoldTimer();
    holdTriggeredRef.current = false;
    pointerPressedRef.current = true;
    hoveredRef.current = true;
    syncVisualState();
    event.currentTarget.setPointerCapture(event.pointerId);

    holdTimerRef.current = window.setTimeout(() => {
      holdTriggeredRef.current = true;
      onHold?.(keySpec.id);
    }, HOLD_DELAY_MS);
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const wasHold = holdTriggeredRef.current;

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    clearPointerPress();
    if (!wasHold) {
      onTap?.(keySpec.id);
    }
  };

  const handlePointerCancel = () => {
    clearPointerPress();
  };

  const handlePointerEnter = () => {
    hoveredRef.current = true;
    syncVisualState();
  };

  const handlePointerLeave = () => {
    hoveredRef.current = false;
    syncVisualState();
  };

  useImperativeHandle(
    ref,
    () => ({
      hover: () => {
        hoveredRef.current = true;
        syncVisualState();
      },
      idle: () => {
        hoveredRef.current = false;
        pointerPressedRef.current = false;
        clearHoldTimer();
        holdTriggeredRef.current = false;
        syncVisualState();
      },
      pressIn: () => {
        clearHoldTimer();
        holdTriggeredRef.current = false;
        pointerPressedRef.current = false;
        latchedPressedRef.current = true;
        setLatchedPressed(true);
        syncVisualState();
      },
      pressOut: () => {
        clearHoldTimer();
        holdTriggeredRef.current = false;
        pointerPressedRef.current = false;
        latchedPressedRef.current = false;
        setLatchedPressed(false);
        syncVisualState();
      },
      resetState: () => {
        hoveredRef.current = false;
        pointerPressedRef.current = false;
        clearHoldTimer();
        holdTriggeredRef.current = false;
        latchedPressedRef.current = false;
        setLatchedPressed(false);
        syncVisualState();
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
    }),
    [],
  );

  useEffect(() => {
    pressedRef.current = pressed;
    syncVisualState();
  }, [pressed]);

  useEffect(() => {
    latchedPressedRef.current = latchedPressed;
    syncVisualState();
  }, [latchedPressed]);

  useEffect(() => {
    onStateChange?.(keySpec.id, visualState);
  }, [keySpec.id, onStateChange, visualState]);

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
      data-state={visualState}
      data-latched={pressed || latchedPressed}
      data-tone={keySpec.tone ?? 'default'}
      data-shape={keySpec.shape ?? 'default'}
      aria-label={effectiveDisplay.a11yLabel ?? effectiveDisplay.label}
      aria-pressed={visualState === 'pressed'}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
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
