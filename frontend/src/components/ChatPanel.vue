<script lang="ts" setup>
  import { ref, watch } from "vue"
  import axios from "axios"
  import type { GowallaPlace } from "@/types/place"

  const props = defineProps<{
    showStr: string
    isExplaining: boolean
    modelValue: boolean
  }>()

  const emit = defineEmits<{
    (e: "update-modelValue", value: boolean): void
  }>()

  const isOpen = ref(props.modelValue)

  watch(
    () => props.modelValue,
    (newVal) => {
      isOpen.value = newVal
    },
  )

  const togglePanel = () => {
    isOpen.value = !isOpen.value
    emit("update-modelValue", isOpen.value)
  }
</script>

<template>
  <div style="position: absolute; bottom: 17px; right: 10px; z-index: 2000; width: 300px">
    <v-card elevation="10" color="secondary">
      <v-card-title
        class="d-flex justify-space-between align-center px-4 py-2 text-subtitle-1 cursor-pointer"
        @click="isOpen = !isOpen">
        <span>
          <v-icon icon="mdi-robot-outline" class="mr-2" />
          LLM Explanation
        </span>
        <v-icon :icon="isOpen ? 'mdi-chevron-down' : 'mdi-chevron-up'" />
      </v-card-title>

      <v-expand-transition>
        <div v-show="isOpen">
          <v-divider />
          <v-card-text class="overflow-y-auto" style="height: 300px; white-space: pre-line">
            <div v-if="isExplaining" class="d-flex flex-column align-center justify-center h-100">
              <v-progress-circular indeterminate color="primary" size="30" />
              <span class="mt-3 text-caption text-grey-lighten-2">Generating explanation...</span>
            </div>
            <span v-else>{{ showStr || "Waiting for inference..." }}</span>
          </v-card-text>
        </div>
      </v-expand-transition>
    </v-card>
  </div>
</template>
