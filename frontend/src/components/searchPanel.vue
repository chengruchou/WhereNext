<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  const searchInput = ref("")
  const emit = defineEmits<{
    (e: "submit-search-place", payload: { placeName: string }): void
  }>()

  const searchPlace = async (query: string) => {
    emit("submit-search-place", { placeName: searchInput.value })
  }
</script>

<template>
  <v-card title="Store place" variant="outlined" class="ma-4" color="success">
    <v-card-item>
      <v-text-field label="Search Location" v-model="searchInput" clearable />
      <v-btn text="search" @click="searchPlace" color="success" />
    </v-card-item>
  </v-card>
</template>
