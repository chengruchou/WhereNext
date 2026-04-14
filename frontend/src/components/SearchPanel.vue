<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  const searchId = ref<number | null>(null)
  const searchCat = ref<string | null>(null)
  const emit = defineEmits<{
    (e: "submit-search-place-id", payload: { passPlaceId: number | null }): void,
    (e: "submit-search-place-cat", payload: { passPlaceCat: string | null }): void
  }>()

  const props = defineProps<{ noSearchRes: boolean, allCat: string [] }>()

  const searchType = ref("id")

  const searchPlaceId = async () => {
    emit("submit-search-place-id", { passPlaceId: searchId.value })
  }

  const searchPlaceCat = async () => {
    emit("submit-search-place-cat", { passPlaceCat: searchCat.value })
  } 
</script>

<template>
  <v-card title="Store place" variant="outlined" class="ma-4" color="success">
    <v-card-text>
      <v-btn-toggle v-model="searchType" color="success" variant="outlined" class="mb-4 w-100">
        <v-btn text="ID" value="id" class="flex-grow-1" />
        <v-btn text="cat" value="cat" class="flex-grow-1" />
      </v-btn-toggle>
        <div v-if="searchType === 'id'" class="d-flex align-center ga-2">
          <v-text-field
            label="Search By ID"
            v-model.number="searchId"
            clearable
            hide-details
            width="90%" />
          <v-btn text="search" @click="searchPlaceId" color="success" width="10%" />
        </div>
        <div v-else class="d-flex align-center ga-2">
          <v-autocomplete
            label="Search By Cat"
            v-model="searchCat"
            :items="props.allCat"
            clearable
            hide-details
            width="90%" />
          <v-btn text="search" @click="searchPlaceCat" color="success" width="10%" />
        </div>
      <v-card-item v-if="props.noSearchRes"> No Search Result </v-card-item>
    </v-card-text>
  </v-card>
</template>
