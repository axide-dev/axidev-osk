import { useEffect, useRef, useState } from 'react';
import KeyButton, { type KeyButtonDisplay } from './components/KeyButton';
import { keyboardLayout } from './layout/usIsoLayout';

const modifierKeyIds = new Set([
  'caps',
  'shift-left',
  'shift-right',
  'ctrl-left',
  'ctrl-right',
  'meta-left',
  'alt-left',
  'alt-right',
]);

function App() {
  const keyboardRef = useRef<HTMLDivElement | null>(null);
  const [latchedModifiers, setLatchedModifiers] = useState<Record<string, boolean>>({});

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

  const handleModifierPressIn = (keyId: string) => {
    console.log('modifier in', keyId);
  };

  const handleModifierPressOut = (keyId: string) => {
    console.log('modifier out', keyId);
  };

  const toggleModifier = (keyId: string) => {
    setLatchedModifiers((currentModifiers) => {
      const isActive = Boolean(currentModifiers[keyId]);

      if (isActive) {
        handleModifierPressOut(keyId);

        return {
          ...currentModifiers,
          [keyId]: false,
        };
      }

      handleModifierPressIn(keyId);

      return {
        ...currentModifiers,
        [keyId]: true,
      };
    });
  };

  const handleTap = (keyId: string) => {
    if (modifierKeyIds.has(keyId)) {
      toggleModifier(keyId);
      return;
    }

    const activeModifiers = Object.entries(latchedModifiers)
      .filter(([, isActive]) => isActive)
      .map(([modifierId]) => modifierId);

    console.log('tap', keyId, { activeModifiers });
  };

  const handleHold = (keyId: string) => {
    console.log('hold', keyId);
  };

  const getKeyDisplay = (keyId: string): KeyButtonDisplay | undefined => {
    if (!latchedModifiers[keyId]) {
      return undefined;
    }

    return {
      legend: 'ON',
    };
  };

  return (
    <div ref={keyboardRef} className="keyboard-grid">
      {keyboardLayout.map((key) => (
        <KeyButton
          key={key.id}
          keySpec={key}
          display={getKeyDisplay(key.id)}
          pressed={Boolean(latchedModifiers[key.id])}
          onTap={handleTap}
          onHold={handleHold}
        />
      ))}
    </div>
  );
}

export default App;
