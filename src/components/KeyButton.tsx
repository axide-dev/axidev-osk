import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import type { KeySpec } from '../layout/usIsoLayout';

type KeyButtonProps = {
  keySpec: KeySpec;
  onTap?: (keyId: string) => void;
  onHold?: (keyId: string) => void;
};

const HOLD_DELAY_MS = 400;

function KeyButton({ keySpec, onTap, onHold }: KeyButtonProps) {
  const holdTimerRef = useRef<number | null>(null);
  const holdTriggeredRef = useRef(false);
  const [isPressed, setIsPressed] = useState(false);

  const style: CSSProperties = {
    gridColumn: `${keySpec.column} / span ${keySpec.width}`,
    gridRow: `${keySpec.row} / span ${keySpec.height ?? 1}`,
  };

  const clearHoldTimer = () => {
    if (holdTimerRef.current !== null) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
  };

  const resetPressState = () => {
    clearHoldTimer();
    setIsPressed(false);
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    clearHoldTimer();
    holdTriggeredRef.current = false;
    setIsPressed(true);
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

    resetPressState();
    if (!wasHold) {
      onTap?.(keySpec.id);
    }
  };

  const handlePointerCancel = () => {
    holdTriggeredRef.current = false;
    resetPressState();
  };

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
      data-pressed={isPressed}
      data-tone={keySpec.tone ?? 'default'}
      data-shape={keySpec.shape ?? 'default'}
      aria-label={keySpec.a11yLabel ?? keySpec.label}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onLostPointerCapture={handlePointerCancel}
      onContextMenu={(event) => event.preventDefault()}
    >
      <span className="key-stack">
        <span className="key-label">{keySpec.label}</span>
        {keySpec.subLabel ? (
          <span className="key-meta">{keySpec.subLabel}</span>
        ) : null}
      </span>
      {keySpec.legend ? <span className="key-meta">{keySpec.legend}</span> : null}
    </button>
  );
}

export default KeyButton;
