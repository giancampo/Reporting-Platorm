/** Client-side row filtering — all filtering happens in the browser against
 * the already-fetched document (action-plan.md §6), never as a new query. */
export interface DimensionFilter {
  dimension: string;
  value: string;
}

export function FilterBar(props: {
  availableDimensions: string[];
  activeFilters: DimensionFilter[];
  onAdd: (filter: DimensionFilter) => void;
  onRemove: (dimension: string) => void;
}) {
  return (
    <div role="toolbar" aria-label="Filters">
      {props.activeFilters.map((filter) => (
        <span key={filter.dimension}>
          {filter.dimension} = {filter.value}
          <button type="button" onClick={() => props.onRemove(filter.dimension)} aria-label={`Remove ${filter.dimension} filter`}>
            ×
          </button>
        </span>
      ))}
    </div>
  );
}
