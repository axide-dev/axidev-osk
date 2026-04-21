import type { KeyButtonConfig } from '../components/keyButton.types';

const stickyModifierButton: KeyButtonConfig = {
  tone: 'accent',
  options: {
    sticky: true,
    stickyMode: 'toggle',
  },
};

export type KeySpec = {
  id: string;
  label: string;
  row: number;
  column: number;
  width: number;
  height?: number;
  subLabel?: string;
  legend?: string;
  a11yLabel?: string;
  button?: KeyButtonConfig;
};

export const keyboardLayout: KeySpec[] = [
  { id: 'esc', label: 'Esc', row: 1, column: 1, width: 2, button: { tone: 'accent' } },
  { id: 'f1', label: 'F1', row: 1, column: 4, width: 2 },
  { id: 'f2', label: 'F2', row: 1, column: 6, width: 2 },
  { id: 'f3', label: 'F3', row: 1, column: 8, width: 2 },
  { id: 'f4', label: 'F4', row: 1, column: 10, width: 2 },
  { id: 'f5', label: 'F5', row: 1, column: 13, width: 2 },
  { id: 'f6', label: 'F6', row: 1, column: 15, width: 2 },
  { id: 'f7', label: 'F7', row: 1, column: 17, width: 2 },
  { id: 'f8', label: 'F8', row: 1, column: 19, width: 2 },
  { id: 'f9', label: 'F9', row: 1, column: 22, width: 2 },
  { id: 'f10', label: 'F10', row: 1, column: 24, width: 2 },
  { id: 'f11', label: 'F11', row: 1, column: 26, width: 2 },
  { id: 'f12', label: 'F12', row: 1, column: 28, width: 2 },

  { id: 'backtick', label: '`', subLabel: '~', row: 2, column: 1, width: 2 },
  { id: 'digit1', label: '1', subLabel: '!', row: 2, column: 3, width: 2 },
  { id: 'digit2', label: '2', subLabel: '@', row: 2, column: 5, width: 2 },
  { id: 'digit3', label: '3', subLabel: '#', row: 2, column: 7, width: 2 },
  { id: 'digit4', label: '4', subLabel: '$', row: 2, column: 9, width: 2 },
  { id: 'digit5', label: '5', subLabel: '%', row: 2, column: 11, width: 2 },
  { id: 'digit6', label: '6', subLabel: '^', row: 2, column: 13, width: 2 },
  { id: 'digit7', label: '7', subLabel: '&', row: 2, column: 15, width: 2 },
  { id: 'digit8', label: '8', subLabel: '*', row: 2, column: 17, width: 2 },
  { id: 'digit9', label: '9', subLabel: '(', row: 2, column: 19, width: 2 },
  { id: 'digit0', label: '0', subLabel: ')', row: 2, column: 21, width: 2 },
  { id: 'minus', label: '-', subLabel: '_', row: 2, column: 23, width: 2 },
  { id: 'equal', label: '=', subLabel: '+', row: 2, column: 25, width: 2 },
  {
    id: 'backspace',
    label: 'Backspace',
    row: 2,
    column: 27,
    width: 4,
    button: { tone: 'action' },
  },

  { id: 'tab', label: 'Tab', row: 3, column: 1, width: 3, button: { tone: 'accent' } },
  { id: 'q', label: 'Q', row: 3, column: 4, width: 2 },
  { id: 'w', label: 'W', row: 3, column: 6, width: 2 },
  { id: 'e', label: 'E', row: 3, column: 8, width: 2 },
  { id: 'r', label: 'R', row: 3, column: 10, width: 2 },
  { id: 't', label: 'T', row: 3, column: 12, width: 2 },
  { id: 'y', label: 'Y', row: 3, column: 14, width: 2 },
  { id: 'u', label: 'U', row: 3, column: 16, width: 2 },
  { id: 'i', label: 'I', row: 3, column: 18, width: 2 },
  { id: 'o', label: 'O', row: 3, column: 20, width: 2 },
  { id: 'p', label: 'P', row: 3, column: 22, width: 2 },
  { id: 'lbracket', label: '[', subLabel: '{', row: 3, column: 24, width: 2 },
  { id: 'rbracket', label: ']', subLabel: '}', row: 3, column: 26, width: 2 },
  {
    id: 'enter',
    label: 'Enter',
    row: 3,
    column: 28,
    width: 3,
    height: 2,
    button: { tone: 'action', shape: 'iso-enter' },
  },

  { id: 'caps', label: 'Caps Lock', row: 4, column: 1, width: 4, button: stickyModifierButton },
  { id: 'a', label: 'A', row: 4, column: 5, width: 2 },
  { id: 's', label: 'S', row: 4, column: 7, width: 2 },
  { id: 'd', label: 'D', row: 4, column: 9, width: 2 },
  { id: 'f', label: 'F', row: 4, column: 11, width: 2 },
  { id: 'g', label: 'G', row: 4, column: 13, width: 2 },
  { id: 'h', label: 'H', row: 4, column: 15, width: 2 },
  { id: 'j', label: 'J', row: 4, column: 17, width: 2 },
  { id: 'k', label: 'K', row: 4, column: 19, width: 2 },
  { id: 'l', label: 'L', row: 4, column: 21, width: 2 },
  { id: 'semicolon', label: ';', subLabel: ':', row: 4, column: 23, width: 2 },
  { id: 'quote', label: "'", subLabel: '"', row: 4, column: 25, width: 2 },
  { id: 'hash', label: '#', subLabel: '~', row: 4, column: 27, width: 1 },

  { id: 'shift-left', label: 'Shift', row: 5, column: 1, width: 3, button: stickyModifierButton },
  { id: 'intl-backslash', label: '\\', subLabel: '|', row: 5, column: 4, width: 1 },
  { id: 'z', label: 'Z', row: 5, column: 5, width: 2 },
  { id: 'x', label: 'X', row: 5, column: 7, width: 2 },
  { id: 'c', label: 'C', row: 5, column: 9, width: 2 },
  { id: 'v', label: 'V', row: 5, column: 11, width: 2 },
  { id: 'b', label: 'B', row: 5, column: 13, width: 2 },
  { id: 'n', label: 'N', row: 5, column: 15, width: 2 },
  { id: 'm', label: 'M', row: 5, column: 17, width: 2 },
  { id: 'comma', label: ',', subLabel: '<', row: 5, column: 19, width: 2 },
  { id: 'period', label: '.', subLabel: '>', row: 5, column: 21, width: 2 },
  { id: 'slash', label: '/', subLabel: '?', row: 5, column: 23, width: 2 },
  { id: 'shift-right', label: 'Shift', row: 5, column: 25, width: 6, button: stickyModifierButton },

  { id: 'ctrl-left', label: 'Ctrl', row: 6, column: 1, width: 3, button: stickyModifierButton },
  { id: 'meta-left', label: 'Win', row: 6, column: 4, width: 3, button: stickyModifierButton },
  { id: 'alt-left', label: 'Alt', row: 6, column: 7, width: 3, button: stickyModifierButton },
  { id: 'space', label: 'Space', row: 6, column: 10, width: 12, button: { tone: 'action' } },
  { id: 'alt-right', label: 'AltGr', row: 6, column: 22, width: 3, button: stickyModifierButton },
  { id: 'fn', label: 'Fn', row: 6, column: 25, width: 2, button: { tone: 'accent' } },
  { id: 'menu', label: 'Menu', row: 6, column: 27, width: 2, button: { tone: 'accent' } },
  { id: 'ctrl-right', label: 'Ctrl', row: 6, column: 29, width: 2, button: stickyModifierButton },
];
