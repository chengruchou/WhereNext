<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { PlaceInfo } from "@/types/place"
  const props = defineProps<{ place: PlaceInfo | null; showAdd: Boolean ; index: number}>()
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: PlaceInfo | null }): void
  }>()

  const addHistory = async () => {
    emit("submit-add-history", { passPlace: props.place })
  }
</script>

<template>
  <v-card v-if="props.place" class="ma-4" elevation="4" variant="outlined" color="warning">
    <v-card-title v-if="props.showAdd"> Place Crad </v-card-title>
    <v-card-title v-else> # {{ props.index + 1 }}</v-card-title>
    <v-img
      v-if="props.place.photoUrl"
      :src="props.place.photoUrl"
      height="150"
      cover
      class="mx-2" />
    <v-card-item>
      <v-card-title>
        {{ props.place.name }}
      </v-card-title>
      <v-card-subtitle>
        {{ props.place.lat.toFixed(4) }}, {{ props.place.lng.toFixed(4) }}
      </v-card-subtitle>
    </v-card-item>
    <v-card-text>
      <v-chip
        v-for="type in props.place.types"
        :key="type"
        size="small"
        class="mr-1 mb-1"
        color="primary"
        variant="tonal">
        {{ type }}
      </v-chip>
      <span v-if="props.showAdd">
        <v-divider class="my-2" thickness="4" />
        <v-btn text="Add to User History" @click="addHistory" block color="warning" />
      </span>
    </v-card-text>
  </v-card>
</template>
