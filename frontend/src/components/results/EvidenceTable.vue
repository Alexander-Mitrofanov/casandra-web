<script setup>
import { ref, useId } from "vue";

defineProps({
  heading: { type: String, required: true },
  caption: { type: String, required: true },
  columns: { type: Array, required: true },
  rows: { type: Array, required: true },
  count: { type: [String, Number], default: null },
  note: { type: String, default: "" },
  empty: { type: String, default: "No results were reported." },
  expandable: { type: Boolean, default: true },
});
const expanded = ref(null);
const tableId = useId();
</script>

<template>
  <details class="evidence-group" open>
    <summary><span>{{ heading }}</span><b>{{ count ?? rows.length }}</b></summary>
    <div v-if="note || $slots.toolbar" class="evidence-table-tools">
      <p v-if="note">{{ note }}</p>
      <slot name="toolbar"/>
    </div>
    <div class="table-scroll" tabindex="0" role="region" :aria-label="`Scrollable ${heading} table`">
      <table class="evidence-table">
        <caption class="sr-only">{{ caption }}</caption>
        <thead><tr>
          <th v-for="column in columns" :key="column.key" scope="col" :class="{ numeric: column.numeric }">{{ column.label }}</th>
          <th v-if="expandable" scope="col" class="evidence-action-heading">Details</th>
        </tr></thead>
        <tbody>
          <template v-for="(row, index) in rows" :key="row.id">
            <tr :class="['evidence-data-row', { 'is-expanded': expanded === row.id }]">
              <component :is="columnIndex === 0 ? 'th' : 'td'" v-for="(column, columnIndex) in columns" :key="column.key" :scope="columnIndex === 0 ? 'row' : undefined" :class="[`evidence-cell-${column.kind || column.key}`, { numeric: column.numeric }]">
                <span v-if="column.kind === 'pill'" :class="['prediction-pill', row.cells[column.key]?.tone]">{{ row.cells[column.key]?.text || '—' }}</span>
                <span v-else-if="column.kind === 'strand'" class="strand" :aria-label="row.cells[column.key]?.accessible">{{ row.cells[column.key]?.text }}</span>
                <span v-else-if="column.kind === 'families'" class="family-composition">{{ row.cells[column.key]?.items?.join(' · ') || '—' }}</span>
                <span v-else>{{ row.cells[column.key]?.text ?? '—' }}</span>
                <small v-if="row.cells[column.key]?.note" class="evidence-cell-note">{{ row.cells[column.key].note }}</small>
              </component>
              <td v-if="expandable" class="evidence-action-cell"><button type="button" class="evidence-toggle" :aria-expanded="expanded === row.id" :aria-controls="`${tableId}-${index}`" :aria-label="`${expanded === row.id ? 'Close' : 'View'} evidence for ${row.label}`" @click="expanded = expanded === row.id ? null : row.id">{{ expanded === row.id ? 'Close' : 'View' }}<span aria-hidden="true">{{ expanded === row.id ? '−' : '+' }}</span></button></td>
            </tr>
            <tr v-if="expandable" v-show="expanded === row.id" class="evidence-detail-row">
              <td :colspan="columns.length + 1">
                <div :id="`${tableId}-${index}`" class="evidence-record" role="region" :aria-label="`Evidence for ${row.label}`">
                  <dl><div v-for="entry in row.details" :key="entry.label" :class="{ 'evidence-detail-wide': entry.wide }">
                    <dt>{{ entry.label }}</dt>
                    <dd><code v-if="entry.code">{{ entry.value }}</code><span v-else>{{ entry.value }}</span><small v-if="entry.note">{{ entry.note }}</small></dd>
                  </div></dl>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="!rows.length"><td :colspan="columns.length + (expandable ? 1 : 0)" class="empty-cell">{{ empty }}</td></tr>
        </tbody>
      </table>
    </div>
  </details>
</template>
