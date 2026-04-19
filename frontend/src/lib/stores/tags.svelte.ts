import * as api from '$lib/api';

class TagStore {
  list = $state<api.Tag[]>([]);
  loading = $state(false);
  error = $state<string | null>(null);

  async refresh(): Promise<void> {
    this.loading = true;
    this.error = null;
    try {
      this.list = await api.listTags();
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    } finally {
      this.loading = false;
    }
  }
}

export const tags = new TagStore();
