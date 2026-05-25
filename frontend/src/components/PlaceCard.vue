<script lang="ts" setup>
  import { computed, ref } from "vue"
  import type { GowallaPlace } from "@/types/place"

  const props = withDefaults(
    defineProps<{
      place: GowallaPlace | null
      showAdd: Boolean
      index: number
      context?: "search" | "recommendation" | "history"
    }>(),
    {
      context: "search",
    },
  )
  const expand = ref(false)
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
  }>()

  const addHistory = async () => {
    emit("submit-add-history", { passPlace: props.place })
  }

  const focusPlace = () => {
    emit("focus-place", { focusPlace: props.place })
  }

  const openDetail = () => {
    if (!props.place) return
    window.open(`http://127.0.0.1:5000/api/poi/detail/${props.place.raw_poi_id}`, "_blank")
  }

  const rankLabel = computed(() => {
    if (!props.showAdd) return `#${props.index + 1}`
    if (props.context === "recommendation") return `Top ${props.index + 1}`
    return "POI"
  })

  const isRecommendation = computed(() => props.context === "recommendation")

  const coordinateText = computed(() => {
    if (!props.place) return ""
    return `${props.place.latitude.toFixed(4)}, ${props.place.longitude.toFixed(4)}`
  })

  const formatCount = (value: number | null) => {
    if (value == null) return null
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
      value,
    )
  }

  const insightChips = computed(() => {
    if (!props.place) return []

    return [
      {
        icon: "mdi-map-marker-check-outline",
        label: "Check-ins",
        value: formatCount(props.place.checkins_count_from_events ?? props.place.checkins_count),
      },
      {
        icon: "mdi-account-group-outline",
        label: "Visitors",
        value: formatCount(props.place.users_count_from_events ?? props.place.users_count),
      },
      {
        icon: "mdi-image-outline",
        label: "Photos",
        value: formatCount(props.place.photos_count),
      },
    ].filter((item) => item.value)
  })
</script>

<template>
  <v-card
    v-if="props.place"
    class="place-card mx-1 my-2"
    elevation="0"
    variant="outlined"
    @click="focusPlace"
    style="cursor: pointer">
    <v-card-item class="pb-2">
      <template #prepend>
        <v-avatar
          class="place-card__rank"
          :color="isRecommendation ? 'primary' : 'surface-variant'"
          variant="flat"
          size="44">
          <span class="place-card__rank-label">{{ rankLabel }}</span>
        </v-avatar>
      </template>

      <v-card-title class="place-card__title text-wrap pa-0">
        {{ props.place.category_name || "Unknown place" }}
      </v-card-title>

      <v-card-subtitle class="place-card__subtitle pa-0 pt-1">
        <v-icon icon="mdi-map-marker-outline" size="15" class="mr-1" />
        {{ coordinateText }}
      </v-card-subtitle>
    </v-card-item>

    <v-card-text class="pt-1 pb-2">
      <div class="d-flex flex-wrap ga-2 mb-3">
        <v-chip size="small" variant="tonal" color="primary" class="place-card__id-chip">
          POI ID: {{ props.place.raw_poi_id }}
        </v-chip>
        <v-chip
          v-if="isRecommendation"
          size="small"
          variant="flat"
          color="primary"
          class="place-card__id-chip">
          Model recommendation
        </v-chip>
      </div>

      <div v-if="insightChips.length > 0" class="d-flex flex-wrap ga-2 mt-3">
        <v-chip
          v-for="item in insightChips"
          :key="item.label"
          size="small"
          variant="tonal"
          color="primary"
          class="place-card__metric">
          <v-icon :icon="item.icon" size="14" start />
          {{ item.value }} {{ item.label }}
        </v-chip>
      </div>
    </v-card-text>

    <v-divider class="mx-4" />

    <v-card-actions class="px-4 py-2">
      <v-btn
        @click.stop="expand = !expand"
        block
        density="comfortable"
        variant="tonal"
        color="primary"
        class="place-card__details-btn">
        Details
        <v-icon
          icon="mdi-chevron-down"
          size="20"
          class="ml-1 place-card__chevron"
          :class="{ 'place-card__chevron--open': expand }" />
      </v-btn>
    </v-card-actions>

    <v-expand-transition>
      <div v-show="expand">
        <v-card-actions v-if="showAdd" class="px-4 pb-2 pt-0">
          <v-btn
            variant="tonal"
            color="primary"
            block
            prepend-icon="mdi-plus"
            @click.stop="addHistory">
            Add to User History
          </v-btn>
        </v-card-actions>

        <v-card-actions class="px-4 pt-0 pb-2">
          <v-btn
            variant="tonal"
            color="secondary"
            block
            prepend-icon="mdi-open-in-new"
            @click.stop="openDetail">
            Show Detail
          </v-btn>
        </v-card-actions>
      </div>
    </v-expand-transition>
  </v-card>
</template>

<style scoped>
  .place-card {
    background: rgb(var(--v-theme-surface));
    border-color: rgba(var(--v-border-color), 0.22);
    overflow: hidden;
    transition:
      border-color 0.18s ease,
      box-shadow 0.18s ease;
  }

  .place-card:hover {
    border-color: rgba(var(--v-theme-primary), 0.45);
    box-shadow: inset 3px 0 0 rgb(var(--v-theme-primary));
  }

  .place-card__rank {
    border: 1px solid rgba(var(--v-theme-primary), 0.32);
    flex-shrink: 0;
    letter-spacing: 0;
  }

  .place-card__rank-label {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0;
    line-height: 1;
  }

  .place-card__title {
    font-size: 1rem;
    font-weight: 800;
    line-height: 1.25;
    color: rgb(var(--v-theme-on-surface));
  }

  .place-card__subtitle {
    align-items: center;
    color: rgba(var(--v-theme-on-surface), 0.78);
    display: flex;
    font-size: 0.78rem;
    line-height: 1.2;
  }

  .place-card__id-chip {
    font-weight: 700;
  }

  .place-card__metric {
    color: rgb(var(--v-theme-on-surface));
    font-weight: 700;
  }

  .place-card__details-btn {
    font-weight: 800;
    letter-spacing: 0;
  }

  .place-card__chevron {
    transition: transform 0.18s ease;
  }

  .place-card__chevron--open {
    transform: rotate(180deg);
  }
</style>
