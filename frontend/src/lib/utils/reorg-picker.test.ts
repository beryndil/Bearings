import { describe, expect, it } from 'vitest';
import { pickerConfirmLabel, pickerTitle, type PickerOp } from './reorg-picker';

describe('pickerTitle', () => {
  it('renders the single-message move title', () => {
    expect(pickerTitle('move', 0)).toBe('Move message to…');
  });

  it('renders the split-from-here title', () => {
    expect(pickerTitle('split', 0)).toBe('Split remaining messages into…');
  });

  it('renders the merge title', () => {
    expect(pickerTitle('merge', 0)).toBe('Merge this session into…');
  });

  it.each([
    [1, 'Move 1 selected message to…'],
    [2, 'Move 2 selected messages to…'],
    [12, 'Move 12 selected messages to…'],
  ])('pluralises bulk-move correctly for %d ids', (count, expected) => {
    expect(pickerTitle('bulk-move', count)).toBe(expected);
  });

  it.each([
    [1, 'Split 1 selected message into a new session'],
    [3, 'Split 3 selected messages into a new session'],
  ])('pluralises bulk-split correctly for %d ids', (count, expected) => {
    expect(pickerTitle('bulk-split', count)).toBe(expected);
  });
});

describe('pickerConfirmLabel', () => {
  it.each<[PickerOp, string]>([
    ['move', 'Move here'],
    ['bulk-move', 'Move here'],
    ['split', 'Split here'],
    ['bulk-split', 'Split here'],
    ['merge', 'Merge here'],
  ])('returns the right confirm label for %s', (op, expected) => {
    expect(pickerConfirmLabel(op)).toBe(expected);
  });
});
