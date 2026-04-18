import * as api from '$lib/api';

class SessionStore {
  list = $state<api.Session[]>([]);
  selectedId = $state<string | null>(null);
  loading = $state(false);
  error = $state<string | null>(null);

  selected = $derived(this.list.find((s) => s.id === this.selectedId) ?? null);

  async refresh(): Promise<void> {
    this.loading = true;
    this.error = null;
    try {
      this.list = await api.listSessions();
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    } finally {
      this.loading = false;
    }
  }

  async create(body: api.SessionCreate): Promise<api.Session | null> {
    this.error = null;
    try {
      const created = await api.createSession(body);
      this.list = [created, ...this.list];
      this.selectedId = created.id;
      return created;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      return null;
    }
  }

  async remove(id: string): Promise<void> {
    this.error = null;
    try {
      await api.deleteSession(id);
      this.list = this.list.filter((s) => s.id !== id);
      if (this.selectedId === id) this.selectedId = null;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    }
  }

  select(id: string | null): void {
    this.selectedId = id;
  }
}

export const sessions = new SessionStore();
