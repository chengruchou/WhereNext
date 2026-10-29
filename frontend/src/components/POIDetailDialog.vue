<script lang="ts" setup>
  import { ref, watch } from 'vue'
  import { api } from '@/api'
  import type { GowallaPlace } from '@/types/place'

  const props = defineProps<{
    modelValue: boolean
    place: GowallaPlace | null
  }>()

  const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void
  }>()

  const loading = ref(false)
  const semanticData = ref<any>(null)
  const error = ref<string | null>(null)

  const fetchDetails = async () => {
    if (!props.place) return
    
    loading.value = true
    error.value = null
    semanticData.value = null
    
    try {
      const response = await api.get(`/poi/detail/${props.place.raw_poi_id}`)
      semanticData.value = response.data
    } catch (err) {
      console.error('Failed to fetch POI semantic details:', err)
      error.value = "Couldn't load this place's details. Try again."
    } finally {
      loading.value = false
    }
  }

  watch(() => props.modelValue, (newVal) => {
    if (newVal && props.place) {
      fetchDetails()
    }
  })

  const close = () => {
    emit('update:modelValue', false)
  }
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="close" max-width="600px" scrollable>
    <v-card class="semantic-dialog">
      <v-toolbar color="surface" density="comfortable" class="semantic-dialog__bar">
        <v-toolbar-title class="text-subtitle-1 font-weight-bold">
          {{ place?.category_name?.trim() || "Place" }}
        </v-toolbar-title>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" aria-label="Close" @click="close" />
      </v-toolbar>

      <v-card-text class="pa-6">
        <div v-if="loading" class="d-flex flex-column align-center py-10">
          <v-progress-circular indeterminate color="primary" size="40" width="4" />
          <div class="mt-4 text-body-2 text-medium-emphasis">Loading place details…</div>
        </div>

        <div v-else-if="error" class="text-center py-10">
          <v-icon icon="mdi-alert-circle-outline" color="error" size="48" />
          <div class="mt-2 text-body-2 text-error">{{ error }}</div>
        </div>

        <div v-else-if="semanticData" class="semantic-content">
          <section class="mb-6">
            <h3 class="semantic-dialog__section">Place</h3>
            <v-row dense>
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis">Place ID</div>
                <div class="text-body-2 font-weight-bold">{{ place?.raw_poi_id }}</div>
              </v-col>
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis">Place type</div>
                <div class="text-body-2 font-weight-bold">{{ semanticData.semantic_information?.cat_name }}</div>
              </v-col>
            </v-row>
          </section>

          <v-divider class="mb-6" />

          <section class="mb-6">
            <h3 class="semantic-dialog__section">Address (OpenStreetMap)</h3>
            <div v-if="semanticData.semantic_information?.address" class="address-grid">
              <v-list density="compact" class="pa-0 bg-transparent">
                <v-list-item v-for="(val, key) in semanticData.semantic_information.address" :key="key" class="px-0">
                  <template #prepend>
                    <v-icon icon="mdi-map-marker-outline" size="18" color="primary" class="mr-2" />
                  </template>
                  <v-list-item-title class="text-caption font-weight-bold text-capitalize">
                    {{ key.replace(/_/g, ' ') }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption">{{ val }}</v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </div>
            <div v-else class="text-caption text-medium-emphasis italic">
              No address found for these coordinates.
            </div>
          </section>

          <v-divider class="mb-6" />

          <section>
            <h3 class="semantic-dialog__section">Coordinates</h3>
            <div class="d-flex align-center ga-4">
              <v-chip size="small" variant="tonal">
                Lat {{ place?.latitude.toFixed(6) }}
              </v-chip>
              <v-chip size="small" variant="tonal">
                Lng {{ place?.longitude.toFixed(6) }}
              </v-chip>
              <v-spacer />
              <v-btn
                variant="outlined"
                color="primary"
                size="small"
                prepend-icon="mdi-google-maps"
                :href="`https://www.google.com/maps/search/?api=1&query=${place?.latitude},${place?.longitude}`"
                target="_blank"
                class="semantic-dialog__link">
                Open in Google Maps
              </v-btn>
            </div>
          </section>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
  .semantic-dialog {
    border-radius: 12px;
    overflow: hidden;
  }
  
  .semantic-content {
    animation: fadeIn 0.3s ease-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .semantic-dialog__bar {
    border-bottom: 1px solid rgba(var(--v-border-color), 0.18);
  }

  .semantic-dialog__section {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.9rem;
    font-weight: 700;
    margin: 0 0 12px;
  }

  .semantic-dialog__link {
    letter-spacing: 0;
    text-transform: none;
  }

  @media (prefers-reduced-motion: reduce) {
    .semantic-content {
      animation: none;
    }
  }
</style>
