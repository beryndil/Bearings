const MODEL_KEY = 'bearings:defaultModel';
const WORKDIR_KEY = 'bearings:defaultWorkingDir';
const TOKEN_KEY = 'bearings:token';
const NOTIFY_KEY = 'bearings:notifyOnComplete';

function readStorage(key: string): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): void {
  if (typeof localStorage === 'undefined') return;
  try {
    if (value === null || value === '') localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Quota/privacy-mode: defaults don't persist, but the UI keeps
    // working for this session.
  }
}

function readBool(key: string): boolean {
  return readStorage(key) === '1';
}

class PrefsStore {
  defaultModel = $state(readStorage(MODEL_KEY) ?? '');
  defaultWorkingDir = $state(readStorage(WORKDIR_KEY) ?? '');
  authToken = $state(readStorage(TOKEN_KEY) ?? '');
  /** Fire a desktop/tray notification when an agent turn finishes.
   * Default off — the first Save in Settings with this checked will
   * trigger the browser's permission prompt via
   * `requestNotifyPermission()`. */
  notifyOnComplete = $state(readBool(NOTIFY_KEY));

  save(values: {
    defaultModel: string;
    defaultWorkingDir: string;
    authToken: string;
    notifyOnComplete: boolean;
  }): void {
    this.defaultModel = values.defaultModel.trim();
    this.defaultWorkingDir = values.defaultWorkingDir.trim();
    this.authToken = values.authToken.trim();
    this.notifyOnComplete = values.notifyOnComplete;
    writeStorage(MODEL_KEY, this.defaultModel || null);
    writeStorage(WORKDIR_KEY, this.defaultWorkingDir || null);
    writeStorage(TOKEN_KEY, this.authToken || null);
    writeStorage(NOTIFY_KEY, this.notifyOnComplete ? '1' : null);
  }
}

export const prefs = new PrefsStore();
