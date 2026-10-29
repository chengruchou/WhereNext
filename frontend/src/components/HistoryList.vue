<script lang="ts" setup>
  import { computed } from "vue"
  import type { GowallaPlace, UserHistory } from "@/types/place"

  const props = defineProps<{ userHistory: UserHistory[] | null }>()

  const emit = defineEmits<{
    (e: "delete-all"): void
    (e: "delete-one", payload: { delId: number }): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
  }>()

  const hasHistory = computed(() => Boolean(props.userHistory && props.userHistory.length > 0))

  const formatTime = (isoString: string | null) => {
    if (!isoString) return "Time unknown"
    const date = new Date(isoString)

    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    })
  }
</script>

<template>
  <section class="history-panel">
    <p v-if="!hasHistory" class="history-panel__empty">
      No visits yet. Find a place on the map and add it.
    </p>

    <template v-else>
      <ol class="history-panel__list">
        <li v-for="(e, index) in props.userHistory" :key="e.log_id" class="history-panel__item">
          <button
            type="button"
            class="history-panel__main"
            :aria-label="`Show visit ${index + 1} on the map`"
            @click="emit('focus-place', { focusPlace: e.poi_detail })">
            <span class="history-panel__index" aria-hidden="true">{{ index + 1 }}</span>
            <span class="history-panel__content">
              <span class="history-panel__name">
                {{ e.poi_detail?.category_name?.trim() || "Unknown place" }}
              </span>
              <span class="history-panel__meta">
                {{ formatTime(e.visit_time) }} · Place {{ e.poi_detail?.raw_poi_id ?? "unknown" }}
              </span>
            </span>
          </button>
          <v-btn
            variant="text"
            size="small"
            density="comfortable"
            icon="mdi-close"
            :aria-label="`Delete visit ${index + 1}`"
            class="history-panel__delete"
            @click="emit('delete-one', { delId: e.log_id })" />
        </li>
      </ol>
      <v-btn size="small" variant="text" class="history-panel__clear" @click="emit('delete-all')">
        Delete all visits
      </v-btn>
    </template>
  </section>
</template>

<style scoped>
  .history-panel__empty {
    color: rgba(var(--v-theme-on-surface), 0.72);
    font-size: 0.8rem;
    line-height: 1.45;
    margin: 0;
  }

  .history-panel__list {
    border: 1px solid rgba(var(--v-border-color), 0.22);
    border-radius: 8px;
    list-style: none;
    margin: 0;
    max-height: 240px;
    overflow-y: auto;
    padding: 4px;
    scrollbar-width: thin;
  }

  .history-panel__item {
    align-items: center;
    display: grid;
    gap: 4px;
    grid-template-columns: minmax(0, 1fr) 32px;
  }

  .history-panel__main {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 6px;
    color: inherit;
    cursor: pointer;
    display: grid;
    gap: 10px;
    grid-template-columns: 24px minmax(0, 1fr);
    padding: 6px;
    text-align: left;
  }

  .history-panel__main:hover {
    background: rgba(var(--v-theme-on-surface), 0.04);
  }

  .history-panel__main:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: -2px;
  }

  .history-panel__index {
    align-items: center;
    background: rgba(var(--v-theme-on-surface), 0.08);
    border-radius: 50%;
    color: rgba(var(--v-theme-on-surface), 0.8);
    display: inline-flex;
    font-size: 0.75rem;
    font-weight: 700;
    height: 24px;
    justify-content: center;
    width: 24px;
  }

  .history-panel__content {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .history-panel__name {
    font-size: 0.85rem;
    font-weight: 700;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .history-panel__meta {
    color: rgba(var(--v-theme-on-surface), 0.64);
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .history-panel__delete {
    color: rgba(var(--v-theme-on-surface), 0.6);
  }

  .history-panel__delete:hover,
  .history-panel__clear:hover {
    color: rgb(var(--v-theme-error));
  }

  .history-panel__clear {
    letter-spacing: 0;
    margin-top: 4px;
    text-transform: none;
  }
</style>
