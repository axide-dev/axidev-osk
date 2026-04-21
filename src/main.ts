import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'node:path';
import started from 'electron-squirrel-startup';
import { installNoActivateClientArea } from '@axidev/electron-client-noactivate';
import {
  initializeKeyboardService,
  registerKeyboardIpc,
  shutdownKeyboardService,
} from './keyboard/service';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

const createWindow = () => {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 1280,
    height: 340,
    minWidth: 1,
    minHeight: 1,
    resizable: true,
    maximizable: true,
    fullscreenable: false,
    autoHideMenuBar: true,
    alwaysOnTop: true,
    useContentSize: true,
    backgroundColor: '#111319',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.setAlwaysOnTop(true, 'floating');
  installNoActivateClientArea(mainWindow);

  // and load the index.html of the app.
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`),
    );
  }

  ipcMain.removeHandler('keyboard:resize-to-content');
  ipcMain.removeAllListeners('keyboard:resize-to-content');
  ipcMain.on('keyboard:resize-to-content', (_event, size) => {
    if (
      typeof size?.width !== 'number' ||
      typeof size?.height !== 'number' ||
      !Number.isFinite(size.width) ||
      !Number.isFinite(size.height)
    ) {
      return;
    }

    const nextWidth = Math.max(320, Math.ceil(size.width));
    const nextHeight = Math.max(160, Math.ceil(size.height));

    mainWindow.setContentSize(nextWidth, nextHeight);
    mainWindow.center();
  });
};

app.whenReady().then(() => {
  registerKeyboardIpc();
  initializeKeyboardService();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  shutdownKeyboardService();
});

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and import them here.
