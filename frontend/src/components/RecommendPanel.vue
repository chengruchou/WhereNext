<script lang="ts" setup>
  import { ref, computed, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  import PlaceCard from "./PlaceCard.vue"

  const props = defineProps<{
    recommendations: GowallaPlace[][]
    isInferring: boolean
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

  const breadcrumbItems = computed(() => {
    return props.recommendations.map((_, index) => ({
      title: `Round ${index + 1}`,
      disabled: false,
    }))
  })
</script>

<template>
  <div class="d-flex flex-column h-100">
    <v-btn
      text="Get next POIs"
      @click="emit('trigger-inference')"
      color="primary"
      :loading="isInferring"
      :disabled="recommendations.length >= 3 || isInferring" />

    <v-breadcrumbs
      v-if="recommendations.length > 0"
      :items="breadcrumbItems"
      class="pa-0"
      divider=">">
      <template v-slot:item="{ item, index }">
        <v-breadcrumbs-item
          :class="{ 'text-primary font-weight-bold': currentRoundIndex === index }"
          style="cursor: pointer"
          @click="setRound(index)">
          {{ item.title }}
        </v-breadcrumbs-item>
      </template>
    </v-breadcrumbs>

    <div class="flex-grow-1 overflow-y-auto pr-1">
      <div v-if="recommendations[currentRoundIndex]" class="d-flex flex-column">
        <PlaceCard
          v-for="(e, idx) in recommendations[currentRoundIndex]"
          :key="e.raw_poi_id || idx"
          :place="e"
          :show-add="true"
          :index="idx"
          @focus-place="emit('focus-place', $event)"
          @submit-add-history="emit('submit-add-history', $event)" />
      </div>
    </div>
  </div>
</template>
