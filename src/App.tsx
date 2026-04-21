import { useEffect, useRef } from 'react';
import KeyButton from './components/KeyButton';
import { keyboardLayout } from './layout/usIsoLayout';

function App() {
  const keyboardRef = useRef<HTMLDivElement | null>(null);

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

  const handleTap = (keyId: string) => {
    console.log('tap', keyId);
  };

  const handleHold = (keyId: string) => {
    console.log('hold', keyId);
  };

  return (
    <div ref={keyboardRef} className="keyboard-grid">
      {keyboardLayout.map((key) => (
        <KeyButton
          key={key.id}
          keySpec={key}
          onTap={handleTap}
          onHold={handleHold}
        />
      ))}
    </div>
  );
}

export default App;
