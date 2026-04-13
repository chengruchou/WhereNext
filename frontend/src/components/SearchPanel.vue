<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  const searchInput = ref<number | null>(null)
  const emit = defineEmits<{
    (e: "submit-search-place", payload: { passPlaceId: number | null }): void
  }>()

  const props = defineProps<{noSearchRes: boolean}>()

  const searchPlace = async () => {
    emit("submit-search-place", { passPlaceId: searchInput.value })
  }
</script>

<template>
  <v-card title="Store place" variant="outlined" class="ma-4" color="success">
    <v-card-text>
      <div class="d-flex align-center ga-2">
        <v-text-field label="Search Location ID" v-model.number="searchInput" clearable hide-details width="90%" />
        <v-btn text="search" @click="searchPlace" color="success" width="10%"/>
      </div>
      <v-card-item v-if="noSearchRes">
        No Search Result
      </v-card-item>
    </v-card-text>
  </v-card>
</template>
