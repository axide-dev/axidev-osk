export type KeyButtonTone = 'default' | 'accent' | 'action';
export type KeyButtonShape = 'default' | 'iso-enter';

export type KeyButtonDisplay = {
  label?: string;
  subLabel?: string;
  legend?: string;
  a11yLabel?: string;
};

export type KeyButtonOptions = {
  holdDelayMs?: number;
  sticky?: boolean;
  stickyMode?: 'toggle' | 'manual';
  defaultLatched?: boolean;
};

export type KeyButtonConfig = {
  tone?: KeyButtonTone;
  shape?: KeyButtonShape;
  display?: KeyButtonDisplay;
  options?: KeyButtonOptions;
};
