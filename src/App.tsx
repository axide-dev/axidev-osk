import { useEffect, useRef, useState } from 'react';
import KeyButton, {
  type KeyButtonDisplay,
  type KeyButtonEvent,
} from './components/KeyButton';
import { keyboardLayout } from './layout/usIsoLayout';
import { getKeyBinding } from './keyboard/keyBindings';
import type {
  KeyboardActionResult,
  KeyboardBridgeState,
} from './keyboard/shared';

function App() {
  const keyboardRef = useRef<HTMLDivElement | null>(null);
  const heldKeyIdsRef = useRef<Set<string>>(new Set());
  const [keyboardState, setKeyboardState] = useState<KeyboardBridgeState | null>(null);

  useEffect(() => {
    const keyboardElement = keyboardRef.current;

    if (!keyboardElement || !window.keyboardWindow) {
      return;
    }

    const resizeWindow = () => {
      const bounds = keyboardElement.getBoundingClientRect();
      window.keyboardWindow?.resizeToContent({
        width: bounds.width,
        height: bounds.height,
      });
    };

    resizeWindow();

    const observer = new ResizeObserver(() => {
      resizeWindow();
    });

    observer.observe(keyboardElement);

    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!window.keyboardIO) {
      return;
    }

    let cancelled = false;

    window.keyboardIO.getState().then((state) => {
      if (!cancelled) {
        setKeyboardState(state);
      }
    });

    const unsubscribe = window.keyboardIO.subscribe((state) => {
      if (!cancelled) {
        setKeyboardState(state);
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const syncActionResult = (result: KeyboardActionResult) => {
    setKeyboardState(result.state);
  };

  const handleTap = async (event: KeyButtonEvent) => {
    if (!window.keyboardIO) {
      return;
    }

    const result = await window.keyboardIO.tapKey(event.keyId);
    syncActionResult(result);
  };

  const handleHold = async (event: KeyButtonEvent) => {
    if (!window.keyboardIO) {
      return;
    }

    const binding = getKeyBinding(event.keyId);

    if (!binding || binding.kind !== 'key') {
      return;
    }

    const result = await window.keyboardIO.pressKey(event.keyId);

    if (result.ok) {
      heldKeyIdsRef.current.add(event.keyId);
    }

    syncActionResult(result);
  };

  const handlePressOut = async (event: KeyButtonEvent) => {
    if (!window.keyboardIO || !heldKeyIdsRef.current.has(event.keyId)) {
      return;
    }

    heldKeyIdsRef.current.delete(event.keyId);
    const result = await window.keyboardIO.releaseKey(event.keyId);
    syncActionResult(result);
  };

  const getKeyDisplay = (keyId: string): KeyButtonDisplay | undefined => {
    if (!keyboardState?.latchedKeyIds.includes(keyId)) {
      return undefined;
    }

    return {
      legend: 'ON',
    };
  };

  const pressedKeyIds = new Set(keyboardState?.pressedKeyIds ?? []);
  const latchedKeyIds = new Set(keyboardState?.latchedKeyIds ?? []);
  const activeModifiers = keyboardState?.activeModifierNames.join(' + ') ?? '';
  const statusText = keyboardState?.error
    ? keyboardState.error
    : keyboardState?.ready
      ? `Connected to ${keyboardState.backendName} (${keyboardState.version})`
      : 'Keyboard bridge is unavailable.';

  return (
    <div ref={keyboardRef} className="keyboard-shell">
      <div className="keyboard-status" data-ready={keyboardState?.ready ?? false}>
        <span>{statusText}</span>
        {activeModifiers ? <span>Active: {activeModifiers}</span> : null}
      </div>
      <div className="keyboard-grid">
        {keyboardLayout.map((key) => {
          const binding = getKeyBinding(key.id);

          return (
            <KeyButton
              key={key.id}
              keySpec={key}
              display={getKeyDisplay(key.id)}
              pressed={pressedKeyIds.has(key.id)}
              latched={latchedKeyIds.has(key.id)}
              disabled={!keyboardState?.ready || binding?.kind === 'unsupported'}
              onTap={handleTap}
              onHold={handleHold}
              onPressOut={handlePressOut}
            />
          );
        })}
      </div>
    </div>
  );
}

export default App;
