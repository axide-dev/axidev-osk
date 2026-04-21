declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;

type KeyboardWindowSize = {
  width: number;
  height: number;
};

interface Window {
  keyboardWindow?: {
    resizeToContent: (size: KeyboardWindowSize) => void;
  };
}
