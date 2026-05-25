<script lang="ts" setup>
  import { ref, computed, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import PlaceCard from "./PlaceCard.vue"

  const props = defineProps<{
    recommendations: GowallaPlace[][]
    isInferring: boolean
    hist: GowallaPlace[] | null
  }>()

  const emit = defineEmits<{
    (e: "trigger-inference"): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
    (e: "update-currentRound", roundIndex: number): void
  }>()

  const currentRoundIndex = ref(0)

  watch(
    () => props.recommendations,
    (newVal) => {
      if (newVal && newVal.length > 0) {
        setRound(newVal.length - 1)
      } else {
        setRound(0)
      }
    },
    { deep: true },
  )

  const setRound = (index: number) => {
    currentRoundIndex.value = index
    emit("update-currentRound", index)
  }

  const stepItems = computed(() => {
    return props.recommendations.map((_, index) => ({
      title: `Step ${index + 1}`,
    }))
  })

  const hasHistory = computed(() => Boolean(props.hist && props.hist.length > 0))
  const hasRecommendations = computed(() => props.recommendations.length > 0)
  const currentRecommendations = computed(() => props.recommendations[currentRoundIndex.value] ?? [])
  const isComplete = computed(() => props.recommendations.length >= 3)

  const actionLabel = computed(() => {
    if (props.isInferring) return "Running inference"
    if (isComplete.value) return "Generated"
    return "Run recommendation model"
  })
</script>

<template>
  <section class="recommend-panel d-flex flex-column h-100">
    <div class="recommend-panel__header">
      <div>
        <div class="text-overline text-primary font-weight-bold">Model Output</div>
        <h2 class="recommend-panel__title">Recommendations</h2>
      </div>

      <v-chip size="small" variant="tonal" color="primary" class="recommend-panel__count">
        {{ recommendations.length }}/3 steps
      </v-chip>
    </div>

    <v-btn
      :text="actionLabel"
      @click="emit('trigger-inference')"
      color="primary"
      variant="flat"
      prepend-icon="mdi-chart-timeline-variant"
      :loading="isInferring"
      :disabled="isComplete || isInferring || !hasHistory"
      class="recommend-panel__action" />

    <v-alert
      v-if="!hasHistory"
      type="info"
      variant="tonal"
      density="compact"
      class="mt-3">
      Load a user history to run inference.
    </v-alert>

    <div v-if="hasRecommendations" class="recommend-panel__steps">
      <v-btn
        v-for="(item, index) in stepItems"
        :key="item.title"
        size="small"
        :variant="currentRoundIndex === index ? 'flat' : 'tonal'"
        color="primary"
        class="recommend-panel__step"
        @click="setRound(index)">
        {{ item.title }}
      </v-btn>
    </div>

    <div class="recommend-panel__body flex-grow-1 overflow-y-auto pr-1">
      <div v-if="currentRecommendations.length > 0" class="d-flex flex-column">
        <PlaceCard
          v-for="(e, idx) in currentRecommendations"
          :key="e.raw_poi_id || idx"
          :place="e"
          :show-add="true"
          :index="idx"
          context="recommendation"
          @focus-place="emit('focus-place', $event)"
          @submit-add-history="emit('submit-add-history', $event)" />
      </div>

      <div v-else class="recommend-panel__empty">
        <v-icon icon="mdi-map-search-outline" size="34" color="primary" />
        <div class="text-body-2 font-weight-bold mt-3">No candidates yet</div>
        <div class="text-caption text-medium-emphasis mt-1">
          Run the model to generate ranked POIs.
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
  .recommend-panel {
    min-height: 0;
  }

  .recommend-panel__header {
    align-items: flex-start;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    display: flex;
    gap: 12px;
    justify-content: space-between;
    padding: 2px 2px 10px;
  }

  .recommend-panel__title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 1.05rem;
    font-weight: 800;
    line-height: 1.25;
    margin: 0;
  }

  .recommend-panel__count {
    flex-shrink: 0;
    font-weight: 700;
    margin-top: 4px;
  }

  .recommend-panel__action {
    font-weight: 800;
    letter-spacing: 0;
    margin-top: 12px;
  }

  .recommend-panel__steps {
    display: grid;
    gap: 6px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    padding: 10px 0 8px;
  }

  .recommend-panel__step {
    font-weight: 700;
    letter-spacing: 0;
    min-width: 0;
  }

  .recommend-panel__body {
    min-height: 0;
    padding-top: 4px;
  }

  .recommend-panel__empty {
    align-items: center;
    border: 1px dashed rgba(var(--v-border-color), 0.28);
    display: flex;
    flex-direction: column;
    justify-content: center;
    margin: 18px 4px 0;
    min-height: 190px;
    padding: 22px;
    text-align: center;
  }
</style>
