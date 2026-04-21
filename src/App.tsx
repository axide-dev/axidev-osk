import { useEffect, useRef, useState } from 'react';
import KeyButton, {
  type KeyButtonDisplay,
  type KeyButtonEvent,
} from './components/KeyButton';
import { keyboardLayout } from './layout/usIsoLayout';

function App() {
  const keyboardRef = useRef<HTMLDivElement | null>(null);
  const [latchedModifiers, setLatchedModifiers] = useState<Record<string, string>>({});

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

  const handleModifierLatchIn = (event: KeyButtonEvent) => {
    setLatchedModifiers((currentModifiers) => ({
      ...currentModifiers,
      [event.keyId]: event.label,
    }));
    console.log('modifier in', event.keyId, event.label);
  };

  const handleModifierLatchOut = (event: KeyButtonEvent) => {
    setLatchedModifiers((currentModifiers) => {
      const nextModifiers = { ...currentModifiers };
      delete nextModifiers[event.keyId];
      return nextModifiers;
    });
    console.log('modifier out', event.keyId, event.label);
  };

  const handleTap = (event: KeyButtonEvent) => {
    console.log('tap', event.keyId, event.label, {
      activeModifiers: Object.values(latchedModifiers),
    });
  };

  const handleHold = (event: KeyButtonEvent) => {
    console.log('hold', event.keyId, event.label);
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
          onTap={handleTap}
          onHold={handleHold}
          onLatchIn={handleModifierLatchIn}
          onLatchOut={handleModifierLatchOut}
        />
      ))}
    </div>
  );
}

export default App;
