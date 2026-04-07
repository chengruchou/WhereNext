<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  interface PlaceInfo {
    name: string
    lat: number
    lng: number
    types: string[]
    photoUrl: string | null
  }
  const props = defineProps<{ place: PlaceInfo | null }>()
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: PlaceInfo | null }): void
  }>()

  const addHistory = async () => {
    emit("submit-add-history", { passPlace: props.place })
  }
</script>

<template>
  <v-card
    v-if="props.place"
    class="ma-4"
    elevation="4"
    title="Place Crad"
    variant="outlined"
    color="warning">
    <v-img v-if="props.place.photoUrl" :src="props.place.photoUrl" height="150" cover />
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
      <v-divider class="my-2" thickness="4" />
      <v-btn text="Add to User History" @click="addHistory" block color="warning" />
    </v-card-text>
  </v-card>
</template>
