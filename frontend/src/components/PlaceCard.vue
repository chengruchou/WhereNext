<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace } from "@/types/place"
  const props = defineProps<{ place: GowallaPlace | null; showAdd: Boolean; index: number }>()
  const emit = defineEmits<{
    (e: "submit-add-history", payload: { passPlace: GowallaPlace | null }): void
  }>()

  const addHistory = async () => {
    emit("submit-add-history", { passPlace: props.place })
  }
</script>

<template>
  <v-card v-if="props.place" class="ma-4" elevation="4" variant="outlined" color="warning">
    <v-card-item>
      <v-card-title>
        {{ props.showAdd ? "Place Card" : `# ${index + 1}` }}
      </v-card-title>
      <template #append>
        <v-chip size="small" variant="tonal" color="warning">
          ID: {{ props.place.raw_poi_id }}
        </v-chip>
      </template>
    </v-card-item>
    <v-divider class="mx-4"></v-divider>
    <v-card-item>
      <v-card-subtitle>
        Pos : ({{ props.place.latitude.toFixed(4) }}, {{ props.place.longitude.toFixed(4) }})
      </v-card-subtitle>
    </v-card-item>
    <v-card-actions v-if="showAdd" class="px-4 pb-4">
      <v-btn variant="flat" color="warning" block @click="addHistory"> Add to User History </v-btn>
    </v-card-actions>
  </v-card>
</template>
