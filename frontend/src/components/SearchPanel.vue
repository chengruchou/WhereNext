<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  const searchInput = ref("")
  const emit = defineEmits<{
    (e: "submit-search-place", payload: { passPlaceName: string }): void
  }>()

  const searchPlace = async () => {
    emit("submit-search-place", { passPlaceName: searchInput.value })
  }
</script>

<template>
  <v-card title="Store place" variant="outlined" class="ma-4" color="success">
    <v-card-text>
      <div class="d-flex align-center ga-2">
        <v-text-field label="Search Location" v-model="searchInput" clearable hide-details width="90%" />
        <v-btn text="search" @click="searchPlace" color="success" width="10%"/>
      </div>
    </v-card-text>
  </v-card>
</template>
