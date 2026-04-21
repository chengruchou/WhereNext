<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  const props = defineProps<{ place: GowallaPlace | null; showAdd: Boolean; index: number }>()
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
  }>()

  const addHistory = async () => {
    emit("submit-add-history", { passPlace: props.place })
  }

  const focusPlace = () => {
    emit("focus-place", { focusPlace: props.place })
  }

  const openDetail = () => {
    if (!props.place) return
    window.open(`http://127.0.0.1:5000/api/poi/detail/${props.place.raw_poi_id}`, "_blank")
  }
</script>

<template>
  <v-card
    v-if="props.place"
    class="ma-4"
    elevation="4"
    variant="outlined"
    color="warning"
    @click="focusPlace"
    style="cursor: pointer">
    <v-card-item>
      <v-card-title class="text-wrap">
        {{ props.showAdd ? "" : `# ${index + 1}` }} {{ props.place.category_name }}
      </v-card-title>
      <template #append>
        <v-chip size="small" variant="tonal" color="warning">
          ID: {{ props.place.raw_poi_id }}
        </v-chip>
      </template>
    </v-card-item>

    <v-divider class="mx-4"></v-divider>

    <v-card-text class="pt-3 pb-2">
      <div class="text-caption text-grey">
        <div class="font-weight-medium mb-1">Coordinates:</div>
        <div>({{ props.place.latitude.toFixed(4) }}, {{ props.place.longitude.toFixed(4) }})</div>
      </div>
    </v-card-text>

    <v-card-actions v-if="showAdd" class="px-4 pb-4">
      <v-btn variant="flat" color="warning" block @click="addHistory"> Add to User History </v-btn>
    </v-card-actions>
    <v-card-actions class="px-4 pb-4">
      <v-btn variant="tonal" color="info" block @click.stop="openDetail"> Show Detail </v-btn>
    </v-card-actions>
  </v-card>
</template>
