<script lang="ts">
  /**
   * Test-only wrapper for `DataView`. Snippets can't be passed from
   * a `render(...)` call directly, so the harness owns the default
   * "success body" snippet locally. Tests drive the four states by
   * threading the boolean / string props.
   *
   * Mirrors the pattern in VirtualItemHarness — kept beside the
   * component so vitest module resolution Just Works.
   */
  import DataView from './DataView.svelte';

  type Props = {
    loading: boolean;
    error: string | null;
    isEmpty: boolean;
    onRetry?: () => void;
    emptyLabel?: string;
    loadingLabel?: string;
    successLabel?: string;
  };

  const {
    loading,
    error,
    isEmpty,
    onRetry,
    emptyLabel,
    loadingLabel,
    successLabel = 'success body'
  }: Props = $props();
</script>

<DataView {loading} {error} {isEmpty} {onRetry} {emptyLabel} {loadingLabel}>
  <div data-testid="dataview-success">{successLabel}</div>
</DataView>
