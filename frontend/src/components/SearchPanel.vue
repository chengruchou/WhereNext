<script lang="ts" setup>
  import { computed, ref, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"

  // Floats over the map: find a place by ID or type, then add it to the traveler's visits.
  const props = defineProps<{
    noSearchRes: boolean
    allCat: string[]
    results: GowallaPlace[]
    canAdd: boolean
  }>()

  const emit = defineEmits<{
    (e: "submit-search-place-id", payload: { passPlaceId: number | null }): void
    (e: "submit-search-place-cat", payload: { passPlaceCat: string | null }): void
    (e: "clear-search-results"): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
  }>()

  const searchId = ref<number | null>(null)
  const searchCat = ref<string | null>(null)
  const formRef = ref<any>(null)
  const validationError = ref<string | null>(null)
  const searchType = ref<"id" | "cat">("id")

  const resultState = computed(() => {
    if (validationError.value) return validationError.value
    if (props.noSearchRes) return "No place matches that search."
    return null
  })

  const idRules = [
    (value: number | string | null) =>
      (value !== null && value !== "") || "Enter a place ID.",
    (value: number | string | null) =>
      Number.isInteger(Number(value)) || "A place ID is a whole number.",
  ]

  watch(searchType, () => {
    validationError.value = null
    if (formRef.value) formRef.value.resetValidation()
  })

  const clearSearchResults = () => {
    validationError.value = null
    emit("clear-search-results")
  }

  const searchPlaceId = async () => {
    validationError.value = null

    const { valid, errors } = await formRef.value.validate()

    if (!valid) {
      if (errors.length > 0) {
        validationError.value = errors[0].errorMessages[0]
      }
      return
    }

    emit("submit-search-place-id", { passPlaceId: searchId.value })
  }

  const searchPlaceCat = async () => {
    validationError.value = null
    emit("submit-search-place-cat", { passPlaceCat: searchCat.value })
  }

  const formatCount = (value: number | null) =>
    value == null ? null : new Intl.NumberFormat("en-US").format(value)
</script>

<template>
  <section class="search-panel" aria-label="Find a place">
    <v-form ref="formRef" class="search-panel__form" @submit.prevent="searchPlaceId">
      <v-btn-toggle
        v-model="searchType"
        density="compact"
        color="primary"
        variant="outlined"
        divided
        mandatory
        class="search-panel__toggle">
        <v-btn value="id" class="search-panel__toggle-btn">ID</v-btn>
        <v-btn value="cat" class="search-panel__toggle-btn">Type</v-btn>
      </v-btn-toggle>

      <v-text-field
        v-if="searchType === 'id'"
        v-model.number="searchId"
        density="compact"
        variant="outlined"
        placeholder="Find a place by ID, e.g. 10028"
        aria-label="Place ID"
        :rules="idRules"
        clearable
        hide-details
        validate-on="submit"
        @click:clear="clearSearchResults" />

      <v-autocomplete
        v-else
        v-model="searchCat"
        :items="props.allCat"
        density="compact"
        variant="outlined"
        :placeholder="`Find a place by type (${props.allCat.length})`"
        aria-label="Place type"
        clearable
        hide-details
        @click:clear="clearSearchResults"
        @update:model-value="searchCat && searchPlaceCat()">
        <template v-slot:item="{ props: itemProps }">
          <v-list-item v-bind="itemProps" class="text-wrap py-2"></v-list-item>
        </template>
      </v-autocomplete>

      <v-btn
        v-if="searchType === 'id'"
        type="submit"
        color="primary"
        variant="tonal"
        icon="mdi-magnify"
        size="small"
        aria-label="Search by place ID" />
    </v-form>

    <p v-if="resultState" class="search-panel__message" role="status">{{ resultState }}</p>

    <template v-if="results.length > 0">
      <div class="search-panel__results-head">
        <span>{{ results.length }} {{ results.length === 1 ? "place" : "places" }}</span>
        <v-btn size="small" variant="text" class="search-panel__clear" @click="clearSearchResults">
          Clear
        </v-btn>
      </div>
      <ul class="search-panel__results">
        <li v-for="place in results" :key="place.raw_poi_id" class="search-panel__result">
          <button
            type="button"
            class="search-panel__result-main"
            :aria-label="`Show ${place.category_name ?? 'place'} ${place.raw_poi_id} on the map`"
            @click="emit('focus-place', { focusPlace: place })">
            <span class="search-panel__result-name">{{ (place.category_name ?? "Place").trim() }}</span>
            <span class="search-panel__result-meta">
              Place {{ place.raw_poi_id }}
              <template v-if="formatCount(place.checkins_count)">
                · {{ formatCount(place.checkins_count) }} check-ins
              </template>
            </span>
          </button>
          <v-tooltip :text="canAdd ? 'Add to visits' : 'Load a traveler first'" location="top">
            <template v-slot:activator="{ props: tip }">
              <span v-bind="tip">
                <v-btn
                  icon="mdi-plus"
                  size="small"
                  variant="text"
                  :disabled="!canAdd"
                  :aria-label="`Add ${place.category_name ?? 'place'} to visits`"
                  @click="emit('submit-add-history', { passPlace: place })" />
              </span>
            </template>
          </v-tooltip>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
  .search-panel {
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgba(var(--v-border-color), 0.22);
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    padding: 8px;
  }

  .search-panel__form {
    align-items: center;
    display: grid;
    gap: 6px;
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .search-panel__toggle {
    height: 40px !important;
  }

  .search-panel__toggle-btn {
    font-weight: 500;
    letter-spacing: 0;
    min-width: 0;
    padding: 0 10px;
    text-transform: none;
  }

  .search-panel__message {
    color: rgb(var(--v-theme-error));
    font-size: 0.8rem;
    margin: 6px 2px 0;
  }

  .search-panel__results-head {
    align-items: center;
    border-top: 1px solid rgba(var(--v-border-color), 0.18);
    color: rgba(var(--v-theme-on-surface), 0.72);
    display: flex;
    font-size: 0.8rem;
    justify-content: space-between;
    margin-top: 8px;
    padding: 4px 2px 0;
  }

  .search-panel__clear {
    letter-spacing: 0;
    text-transform: none;
  }

  .search-panel__results {
    list-style: none;
    margin: 0;
    max-height: 40vh;
    overflow-y: auto;
    padding: 0;
    scrollbar-width: thin;
  }

  .search-panel__result {
    align-items: center;
    display: grid;
    gap: 4px;
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .search-panel__result-main {
    background: none;
    border: 0;
    border-radius: 6px;
    color: inherit;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 6px;
    text-align: left;
  }

  .search-panel__result-main:hover {
    background: rgba(var(--v-theme-on-surface), 0.04);
  }

  .search-panel__result-main:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: -2px;
  }

  .search-panel__result-name {
    font-size: 0.85rem;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .search-panel__result-meta {
    color: rgba(var(--v-theme-on-surface), 0.64);
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
  }
</style>
