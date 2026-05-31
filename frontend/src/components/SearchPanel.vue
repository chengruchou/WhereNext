<script lang="ts" setup>
  import { computed, ref, watch } from "vue"

  const props = defineProps<{ noSearchRes: boolean; allCat: string[] }>()

  const emit = defineEmits<{
    (e: "submit-search-place-id", payload: { passPlaceId: number | null }): void
    (e: "submit-search-place-cat", payload: { passPlaceCat: string | null }): void
    (e: "clear-search-results"): void
  }>()

  const searchId = ref<number | null>(null)
  const searchCat = ref<string | null>(null)
  const formRef = ref<any>(null)
  const validationError = ref<string | null>(null)
  const searchType = ref<"id" | "cat">("id")

  const resultState = computed(() => {
    if (validationError.value) return validationError.value
    if (props.noSearchRes) return "No matching candidate found."
    return null
  })

  const idRules = [
    (value: number | string | null) =>
      (value !== null && value !== "") || "POI ID is required.",
    (value: number | string | null) =>
      Number.isInteger(Number(value)) || "POI ID must be an integer.",
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
</script>

<template>
  <section class="search-panel">
    <div class="search-panel__header">
      <div class="search-panel__heading">
        <div class="text-overline text-success font-weight-bold">Search Space</div>
        <h2 class="search-panel__title">Candidate POIs</h2>
      </div>

      <v-chip size="small" variant="tonal" color="success" class="search-panel__count">
        {{ props.allCat.length }} categories
      </v-chip>
    </div>

    <v-card class="search-panel__card" elevation="0" variant="outlined">
      <v-card-text class="pa-3">
        <v-btn-toggle
          density="compact"
          v-model="searchType"
          color="success"
          variant="outlined"
          divided
          mandatory
          class="search-panel__toggle">
          <v-btn value="id" class="search-panel__toggle-btn">
            <v-icon icon="mdi-pound" size="16" start />
            ID
          </v-btn>
          <v-btn value="cat" class="search-panel__toggle-btn">
            <v-icon icon="mdi-shape-outline" size="16" start />
            Category
          </v-btn>
        </v-btn-toggle>

        <v-form ref="formRef" @submit.prevent="searchPlaceId">
          <div v-if="searchType === 'id'" class="search-panel__form">
            <v-text-field
              density="compact"
              label="POI ID"
              v-model.number="searchId"
              :rules="idRules"
              clearable
              @click:clear="clearSearchResults"
              hide-details="auto"
              validate-on="submit"
              variant="outlined" />

            <v-tooltip text="Search by POI ID" location="top">
              <template v-slot:activator="{ props: tooltipProps }">
                <v-btn
                  v-bind="tooltipProps"
                  type="submit"
                  color="success"
                  icon="mdi-magnify"
                  aria-label="Search by POI ID"
                  class="search-panel__action" />
              </template>
            </v-tooltip>
          </div>

          <div v-else class="search-panel__form">
            <v-autocomplete
              density="compact"
              label="Category"
              v-model="searchCat"
              :items="props.allCat"
              clearable
              @click:clear="clearSearchResults"
              hide-details="auto"
              variant="outlined">
              <template v-slot:item="{ props: itemProps }">
                <v-list-item v-bind="itemProps" class="text-wrap py-2"></v-list-item>
              </template>
            </v-autocomplete>

            <v-tooltip text="Search by category" location="top">
              <template v-slot:activator="{ props: tooltipProps }">
                <v-btn
                  v-bind="tooltipProps"
                  @click="searchPlaceCat"
                  :disabled="!searchCat || !props.allCat.includes(searchCat)"
                  color="success"
                  icon="mdi-magnify"
                  aria-label="Search by category"
                  class="search-panel__action" />
              </template>
            </v-tooltip>
          </div>
        </v-form>

        <v-alert
          v-if="resultState"
          type="error"
          variant="tonal"
          density="compact"
          class="search-panel__alert">
          {{ resultState }}
        </v-alert>
      </v-card-text>
    </v-card>
  </section>
</template>

<style scoped>
  .search-panel {
    margin: 0 4px 14px;
  }

  .search-panel__header {
    align-items: flex-start;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
    display: flex;
    gap: 12px;
    justify-content: space-between;
    padding: 2px 2px 10px;
  }

  .search-panel__heading {
    min-width: 0;
  }

  .search-panel__title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 1.05rem;
    font-weight: 800;
    line-height: 1.25;
    margin: 0;
  }

  .search-panel__count {
    flex-shrink: 0;
    font-weight: 700;
    margin-top: 4px;
  }

  .search-panel__card {
    background: rgb(var(--v-theme-surface));
    border-color: rgba(var(--v-border-color), 0.22);
    margin-top: 12px;
  }

  .search-panel__toggle {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-bottom: 12px;
    width: 100%;
  }

  .search-panel__toggle-btn {
    font-weight: 800;
    letter-spacing: 0;
    min-width: 0;
  }

  .search-panel__form {
    align-items: flex-start;
    display: grid;
    gap: 10px;
    grid-template-columns: minmax(0, 1fr) 48px;
  }

  .search-panel__action {
    height: 40px;
    letter-spacing: 0;
    min-width: 40px;
    width: 48px;
  }

  .search-panel__alert {
    margin-top: 10px;
  }

  @media (max-width: 720px) {
    .search-panel__form {
      grid-template-columns: 1fr;
    }

    .search-panel__action {
      width: 100%;
    }
  }
</style>
