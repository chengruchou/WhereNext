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
  const historyCount = computed(() => props.userHistory?.length ?? 0)

  const deleteAll = async () => {
    emit("delete-all")
  }

  const deleteOne = async (id: number) => {
    emit("delete-one", { delId: id })
  }

  const formatTime = (isoString: string | null) => {
    if (!isoString) return "Time unavailable"
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
    <div class="history-panel__header">
      <div class="history-panel__heading">
        <div class="text-overline text-secondary font-weight-bold">User History</div>
        <h2 class="history-panel__title">Observed Visits</h2>
      </div>

      <div class="history-panel__actions">
        <v-chip size="small" variant="tonal" color="secondary" class="history-panel__count">
          {{ historyCount }} visits
        </v-chip>

        <v-tooltip text="Delete all visits" location="top">
          <template v-slot:activator="{ props: tooltipProps }">
            <v-btn 
              v-if="hasHistory" 
              v-bind="tooltipProps"
              color="error" 
              variant="tonal" 
              size="small"
              density="comfortable"
              icon="mdi-delete-sweep-outline" 
              class="history-panel__clear"
              @click.stop="deleteAll"
            />
          </template>
        </v-tooltip>
      </div>
    </div>

    <v-card class="history-panel__card" elevation="0" variant="outlined">
      <div v-if="!hasHistory" class="history-panel__empty">
        <v-icon icon="mdi-timeline-clock-outline" size="30" color="secondary" />
        <div class="history-panel__empty-title">No visits loaded</div>
        <div class="history-panel__empty-text">Select a user to inspect historical check-ins.</div>
      </div>

      <div v-else class="history-panel__body">
        <button
          v-for="(e, index) in props.userHistory"
          :key="e.log_id"
          type="button"
          class="history-panel__item"
          @click="emit('focus-place', { focusPlace: e.poi_detail })">
          <span class="history-panel__index">{{ index + 1 }}</span>

          <span class="history-panel__content">
            <span class="history-panel__name">
              {{ e.poi_detail?.category_name || "Unknown POI" }}
            </span>

            <span class="history-panel__meta">
              <v-icon icon="mdi-clock-outline" size="14" />
              {{ formatTime(e.visit_time) }}
            </span>

            <span class="history-panel__meta">
              <v-icon icon="mdi-map-marker-outline" size="14" />
              POI ID: {{ e.poi_detail?.raw_poi_id ?? "N/A" }}
            </span>
          </span>

          <v-tooltip text="Delete this visit" location="top">
            <template v-slot:activator="{ props: tooltipProps }">
              <v-btn
                v-bind="tooltipProps"
                color="error"
                variant="text"
                size="small"
                density="comfortable"
                icon="mdi-delete-outline"
                class="history-panel__delete"
                @click.stop="deleteOne(e.log_id)" 
              />
            </template>
          </v-tooltip>
        </button>
      </div>
    </v-card>
  </section>
</template>

<style scoped>
  .history-panel {
    margin: 0 4px 14px;
  }

  .history-panel__header {
    align-items: flex-start;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    display: flex;
    gap: 12px;
    justify-content: space-between;
    padding: 2px 2px 10px;
  }

  .history-panel__heading {
    min-width: 0;
  }

  .history-panel__title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 1.05rem;
    font-weight: 800;
    line-height: 1.25;
    margin: 0;
  }

  .history-panel__actions {
    align-items: center;
    display: flex;
    flex-shrink: 0;
    gap: 6px;
    margin-top: 3px;
  }

  .history-panel__count {
    font-weight: 700;
  }

  .history-panel__clear {
    flex-shrink: 0;
  }

  .history-panel__card {
    background: rgb(var(--v-theme-surface));
    border-color: rgba(var(--v-border-color), 0.22);
    margin-top: 12px;
    overflow: hidden;
  }

  .history-panel__empty {
    align-items: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 150px;
    padding: 22px 16px;
    text-align: center;
  }

  .history-panel__empty-title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.9rem;
    font-weight: 800;
    margin-top: 10px;
  }

  .history-panel__empty-text {
    color: rgba(var(--v-theme-on-surface), 0.68);
    font-size: 0.76rem;
    line-height: 1.35;
    margin-top: 3px;
  }

  .history-panel__body {
    max-height: 210px;
    overflow-y: auto;
    padding: 6px;
  }

  .history-panel__item {
    align-items: flex-start;
    background: transparent;
    border: 0;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.16);
    color: inherit;
    cursor: pointer;
    display: grid;
    gap: 10px;
    grid-template-columns: 30px minmax(0, 1fr) 32px;
    min-height: 64px;
    padding: 8px 4px;
    text-align: left;
    width: 100%;
  }

  .history-panel__item:last-child {
    border-bottom: 0;
  }

  .history-panel__item:hover {
    background: rgba(var(--v-theme-secondary), 0.07);
  }

  .history-panel__index {
    align-items: center;
    background: rgba(var(--v-theme-secondary), 0.14);
    border: 1px solid rgba(var(--v-theme-secondary), 0.24);
    color: rgb(var(--v-theme-on-surface));
    display: inline-flex;
    font-size: 0.74rem;
    font-weight: 800;
    height: 28px;
    justify-content: center;
    line-height: 1;
    margin-top: 1px;
    min-width: 28px;
  }

  .history-panel__content {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .history-panel__name {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.88rem;
    font-weight: 800;
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .history-panel__meta {
    align-items: center;
    color: rgba(var(--v-theme-on-surface), 0.68);
    display: flex;
    font-size: 0.74rem;
    gap: 4px;
    line-height: 1.25;
    margin-top: 4px;
    min-width: 0;
  }

  .history-panel__delete {
    margin-top: -2px;
  }
</style>
