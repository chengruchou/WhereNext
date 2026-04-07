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
</script>

<template>
  <v-card v-if="props.place" class="ma-4" elevation="4" title="Place Crad">
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
    </v-card-text>
    <v-btn text="Add to User History" block color="warning"/>
  </v-card>
</template>
