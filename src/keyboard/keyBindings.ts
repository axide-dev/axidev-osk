export type KeyboardModifierName =
  | 'Shift'
  | 'Ctrl'
  | 'Alt'
  | 'Super'
  | 'CapsLock';

export type KeyBinding =
  | {
      kind: 'key';
      input: string;
      eventNames: readonly string[];
    }
  | {
      kind: 'modifier';
      input: string;
      modifier: KeyboardModifierName;
      eventNames: readonly string[];
    }
  | {
      kind: 'unsupported';
      reason: string;
      eventNames: readonly string[];
    };

const bindKey = (
  input: string,
  eventNames: readonly string[] = [input],
): KeyBinding => ({
  kind: 'key',
  input,
  eventNames,
});

const bindModifier = (
  input: string,
  modifier: KeyboardModifierName,
  eventNames: readonly string[] = [input],
): KeyBinding => ({
  kind: 'modifier',
  input,
  modifier,
  eventNames,
});

const unsupported = (reason: string): KeyBinding => ({
  kind: 'unsupported',
  reason,
  eventNames: [],
});

export const keyBindings: Record<string, KeyBinding> = {
  esc: bindKey('Escape'),
  f1: bindKey('F1'),
  f2: bindKey('F2'),
  f3: bindKey('F3'),
  f4: bindKey('F4'),
  f5: bindKey('F5'),
  f6: bindKey('F6'),
  f7: bindKey('F7'),
  f8: bindKey('F8'),
  f9: bindKey('F9'),
  f10: bindKey('F10'),
  f11: bindKey('F11'),
  f12: bindKey('F12'),
  backtick: bindKey('`'),
  digit1: bindKey('1'),
  digit2: bindKey('2'),
  digit3: bindKey('3'),
  digit4: bindKey('4'),
  digit5: bindKey('5'),
  digit6: bindKey('6'),
  digit7: bindKey('7'),
  digit8: bindKey('8'),
  digit9: bindKey('9'),
  digit0: bindKey('0'),
  minus: bindKey('-'),
  equal: bindKey('='),
  backspace: bindKey('Backspace'),
  tab: bindKey('Tab'),
  q: bindKey('Q'),
  w: bindKey('W'),
  e: bindKey('E'),
  r: bindKey('R'),
  t: bindKey('T'),
  y: bindKey('Y'),
  u: bindKey('U'),
  i: bindKey('I'),
  o: bindKey('O'),
  p: bindKey('P'),
  lbracket: bindKey('['),
  rbracket: bindKey(']'),
  enter: bindKey('Enter'),
  caps: bindModifier('CapsLock', 'CapsLock'),
  a: bindKey('A'),
  s: bindKey('S'),
  d: bindKey('D'),
  f: bindKey('F'),
  g: bindKey('G'),
  h: bindKey('H'),
  j: bindKey('J'),
  k: bindKey('K'),
  l: bindKey('L'),
  semicolon: bindKey(';'),
  quote: bindKey("'"),
  hash: bindKey('Hash', ['Hashtag']),
  'shift-left': bindModifier('ShiftLeft', 'Shift'),
  'intl-backslash': bindKey('\\'),
  z: bindKey('Z'),
  x: bindKey('X'),
  c: bindKey('C'),
  v: bindKey('V'),
  b: bindKey('B'),
  n: bindKey('N'),
  m: bindKey('M'),
  comma: bindKey(','),
  period: bindKey('.'),
  slash: bindKey('/'),
  'shift-right': bindModifier('ShiftRight', 'Shift'),
  'ctrl-left': bindModifier('CtrlLeft', 'Ctrl'),
  'meta-left': bindModifier('SuperLeft', 'Super'),
  'alt-left': bindModifier('AltLeft', 'Alt'),
  space: bindKey('Space'),
  'alt-right': bindModifier('AltRight', 'Alt'),
  fn: unsupported('Fn is not exposed by @axidev/io.'),
  menu: bindKey('Menu'),
  'ctrl-right': bindModifier('CtrlRight', 'Ctrl'),
};

export function getKeyBinding(keyId: string): KeyBinding | undefined {
  return keyBindings[keyId];
}

export function createListenerKeyIndex(): Map<string, string[]> {
  const listenerKeyIndex = new Map<string, string[]>();

  Object.entries(keyBindings).forEach(([keyId, binding]) => {
    binding.eventNames.forEach((eventName) => {
      const existing = listenerKeyIndex.get(eventName);

      if (existing) {
        existing.push(keyId);
        return;
      }

      listenerKeyIndex.set(eventName, [keyId]);
    });
  });

  return listenerKeyIndex;
}
