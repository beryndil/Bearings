const MODEL_KEY = 'bearings:defaultModel';
const WORKDIR_KEY = 'bearings:defaultWorkingDir';
const TOKEN_KEY = 'bearings:token';

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

class PrefsStore {
  defaultModel = $state(readStorage(MODEL_KEY) ?? '');
  defaultWorkingDir = $state(readStorage(WORKDIR_KEY) ?? '');
  authToken = $state(readStorage(TOKEN_KEY) ?? '');

  save(values: { defaultModel: string; defaultWorkingDir: string; authToken: string }): void {
    this.defaultModel = values.defaultModel.trim();
    this.defaultWorkingDir = values.defaultWorkingDir.trim();
    this.authToken = values.authToken.trim();
    writeStorage(MODEL_KEY, this.defaultModel || null);
    writeStorage(WORKDIR_KEY, this.defaultWorkingDir || null);
    writeStorage(TOKEN_KEY, this.authToken || null);
  }
}

export const prefs = new PrefsStore();
