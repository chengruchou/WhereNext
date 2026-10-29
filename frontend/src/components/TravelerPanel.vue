<script lang="ts" setup>
  import { computed, ref } from "vue"
  import type { GowallaPlace, UserHistory } from "@/types/place"
  import HistoryList from "./HistoryList.vue"
  import StepHeading from "./StepHeading.vue"
  import UserLogin from "./UserLogin.vue"

  const props = defineProps<{
    userId: number | null
    userHistory: UserHistory[]
  }>()

  const emit = defineEmits<{
    (e: "submit-user-id", payload: { passUserId: number | null }): void
    (e: "delete-all"): void
    (e: "delete-one", payload: { delId: number }): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
  }>()

  // The visits fold into one line, so the request and the route stay in view.
  const showVisits = ref(false)

  const summary = computed(() => {
    const visits = props.userHistory
    if (visits.length === 0) return "No visits yet"
    const last = visits.at(-1)?.poi_detail?.category_name?.trim() || "unknown place"
    return `${visits.length} ${visits.length === 1 ? "visit" : "visits"}, last at ${last}`
  })
</script>

<template>
  <section class="traveler-panel">
    <StepHeading :step="1" title="Traveler" />
    <UserLogin @submit-user-id="emit('submit-user-id', $event)" />

    <template v-if="userId != null">
      <button
        type="button"
        class="traveler-panel__summary"
        :aria-expanded="showVisits"
        @click="showVisits = !showVisits">
        <span>{{ summary }}</span>
        <span class="traveler-panel__toggle">
          {{ showVisits ? "Hide" : "Show" }}
          <v-icon :icon="showVisits ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="16" />
        </span>
      </button>

      <HistoryList
        v-if="showVisits"
        :user-history="userHistory"
        @delete-all="emit('delete-all')"
        @delete-one="emit('delete-one', $event)"
        @focus-place="emit('focus-place', $event)" />
    </template>
  </section>
</template>

<style scoped>
  .traveler-panel {
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    margin-bottom: 14px;
    padding-bottom: 14px;
  }

  .traveler-panel__summary {
    align-items: center;
    background: none;
    border: 0;
    border-radius: 4px;
    color: rgba(var(--v-theme-on-surface), 0.8);
    cursor: pointer;
    display: flex;
    font-size: 0.82rem;
    gap: 8px;
    justify-content: space-between;
    margin: 8px 0 6px;
    padding: 2px 0;
    text-align: left;
    width: 100%;
  }

  .traveler-panel__summary:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: 2px;
  }

  .traveler-panel__toggle {
    align-items: center;
    color: rgb(var(--v-theme-primary));
    display: inline-flex;
    flex-shrink: 0;
    font-size: 0.78rem;
  }
</style>
