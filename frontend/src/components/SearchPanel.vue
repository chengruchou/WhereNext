<script lang="ts" setup>
  import { ref, watch } from "vue"

  const searchId = ref<number | null>(null)
  const searchCat = ref<string | null>(null)
  const formRef = ref<any>(null)
  const validationError = ref<string | null>(null) // New ref to hold our custom error text

  const emit = defineEmits<{
    (e: "submit-search-place-id", payload: { passPlaceId: number | null }): void
    (e: "submit-search-place-cat", payload: { passPlaceCat: string | null }): void
  }>()

  const props = defineProps<{ noSearchRes: boolean; allCat: string[] }>()

  const searchType = ref("id")

  const idRules = [
    (value: any) => !!value || "Place ID is required.",
    (value: any) => Number.isInteger(Number(value)) || "Place ID must be a number.",
  ]

  // Clear errors when swapping between ID and Cat search
  watch(searchType, () => {
    validationError.value = null
    if (formRef.value) formRef.value.resetValidation()
  })

  const searchPlaceId = async () => {
    validationError.value = null // Reset error on new search attempt

    const { valid, errors } = await formRef.value.validate()

    if (!valid) {
      // Grab the first error message from Vuetify's validation check
      if (errors.length > 0) {
        validationError.value = errors[0].errorMessages[0]
      }
      return
    }

    emit("submit-search-place-id", { passPlaceId: searchId.value })
  }

  const searchPlaceCat = async () => {
    validationError.value = null // Reset error here too just in case
    // (Optional: add validation for searchCat here if needed!)
    emit("submit-search-place-cat", { passPlaceCat: searchCat.value })
  }
</script>

<template>
  <v-card title="Store place" variant="outlined" class="ma-4" color="success">
    <v-card-text>
      <v-btn-toggle
        density="compact"
        v-model="searchType"
        color="success"
        variant="outlined"
        class="mb-4 w-100">
        <v-btn text="ID" value="id" class="flex-grow-1" />
        <v-btn text="Cat." value="cat" class="flex-grow-1" />
      </v-btn-toggle>

      <v-form ref="formRef" @submit.prevent="searchPlaceId">
        <div v-if="searchType === 'id'" class="d-flex align-center ga-2">
          <v-text-field
            density="compact"
            label="Search By ID"
            v-model.number="searchId"
            :rules="idRules"
            hide-details
            width="90%"
            validate-on="submit" />
          <v-btn type="submit" text="Search" color="success" width="10%" />
        </div>

        <div v-else class="d-flex align-center ga-2">
          <v-tooltip :text="searchCat || ''" :disabled="!searchCat" location="top">
            <template v-slot:activator="{ props: tooltipProps }">
              <div v-bind="tooltipProps" style="width: 90%">
                <v-autocomplete
                  density="compact"
                  label="Search By Cat."
                  v-model="searchCat"
                  :items="props.allCat"
                  hide-details>
                  <template v-slot:item="{ props: itemProps }">
                    <v-list-item v-bind="itemProps" class="text-wrap py-2"></v-list-item>
                  </template>
                </v-autocomplete>
              </div>
            </template>
          </v-tooltip>

          <v-btn
            text="Search"
            @click="searchPlaceCat"
            :disabled="!searchCat || !props.allCat.includes(searchCat)"
            color="success"
            width="10%" />
        </div>
      </v-form>

      <v-card-item
        v-if="validationError || props.noSearchRes"
        class="text-error font-weight-bold pb-0">
        {{ validationError || "No Search Result Found" }}
      </v-card-item>
    </v-card-text>
  </v-card>
</template>
