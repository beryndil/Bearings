import { describe, expect, it } from 'vitest';
import { extractPaths, hasFiles, parseUriList } from './composer-dragdrop';

describe('parseUriList', () => {
  it('extracts file:// paths', () => {
    expect(parseUriList('file:///home/dave/notes.md')).toEqual(['/home/dave/notes.md']);
  });

  it('skips comments and blank lines per RFC 2483', () => {
    const input = ['# from Dolphin', '', 'file:///a.txt', '   ', 'file:///b.txt'].join('\n');
    expect(parseUriList(input)).toEqual(['/a.txt', '/b.txt']);
  });

  it('drops non-file schemes silently', () => {
    expect(parseUriList('https://example.com/x\nfile:///kept')).toEqual(['/kept']);
  });

  it('drops file URIs with non-localhost authority', () => {
    expect(parseUriList('file://remote-host/secret')).toEqual([]);
    // Empty authority is the "local" case and stays.
    expect(parseUriList('file:///local')).toEqual(['/local']);
    // Explicit localhost stays too.
    expect(parseUriList('file://localhost/local')).toEqual(['/local']);
  });

  it('decodes percent-escaped paths so spaces and unicode round-trip', () => {
    expect(parseUriList('file:///home/dave/My%20Notes.md')).toEqual([
      '/home/dave/My Notes.md'
    ]);
  });

  it('swallows malformed URIs without throwing', () => {
    expect(parseUriList('file://not a url at all')).toEqual([]);
  });
});

describe('hasFiles', () => {
  it('is true when DataTransfer.types contains Files', () => {
    const evt = {
      dataTransfer: { types: ['Files', 'text/uri-list'] }
    } as unknown as DragEvent;
    expect(hasFiles(evt)).toBe(true);
  });

  it('is false when types lacks Files', () => {
    const evt = {
      dataTransfer: { types: ['text/plain'] }
    } as unknown as DragEvent;
    expect(hasFiles(evt)).toBe(false);
  });

  it('is false when there is no dataTransfer (synthetic events)', () => {
    expect(hasFiles({} as DragEvent)).toBe(false);
  });
});

describe('extractPaths', () => {
  function fakeDataTransfer(payloads: Record<string, string>): DataTransfer {
    return {
      getData(fmt: string) {
        return payloads[fmt] ?? '';
      }
    } as unknown as DataTransfer;
  }

  it('returns paths and a formats trace for text/uri-list', () => {
    const dt = fakeDataTransfer({ 'text/uri-list': 'file:///a\nfile:///b' });
    const { paths, formats } = extractPaths(dt);
    expect(paths.sort()).toEqual(['/a', '/b']);
    expect(formats).toEqual(['text/uri-list=file:///a\nfile:///b']);
  });

  it('falls back to raw absolute paths in text/plain', () => {
    const dt = fakeDataTransfer({ 'text/plain': '/home/dave/raw.txt' });
    const { paths } = extractPaths(dt);
    expect(paths).toEqual(['/home/dave/raw.txt']);
  });

  it('dedupes paths surfacing in multiple formats', () => {
    const dt = fakeDataTransfer({
      'text/uri-list': 'file:///shared',
      'text/plain': '/shared'
    });
    const { paths } = extractPaths(dt);
    expect(paths).toEqual(['/shared']);
  });

  it('skips raw-path candidates that contain spaces', () => {
    // Spaces in a `text/plain` payload usually mean "this is a
    // sentence the user dragged," not a path. Skipping avoids
    // ingesting prose at the cursor.
    const dt = fakeDataTransfer({ 'text/plain': '/home/dave with space' });
    const { paths } = extractPaths(dt);
    expect(paths).toEqual([]);
  });

  it('truncates each format value at 200 chars in the trace', () => {
    const long = 'file:///' + 'a'.repeat(400);
    const dt = fakeDataTransfer({ 'text/uri-list': long });
    const { formats } = extractPaths(dt);
    expect(formats[0]).toMatch(/^text\/uri-list=/);
    // 200 chars after the `text/uri-list=` prefix.
    expect(formats[0].length).toBe('text/uri-list='.length + 200);
  });
});
