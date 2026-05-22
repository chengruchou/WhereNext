<script lang="ts" setup>
  import { ref } from "vue"
  import axios from "axios"
  import type { GowallaPlace } from "@/types/place"

  const props = defineProps<{ showStr: string; isExplaining: boolean }>()

  const emit = defineEmits<{ (e: "generate-explanation"): void }>()

  const generateExplanation = async () => {
    emit("generate-explanation")
  }
</script>

<template>
  <div style="position: absolute; bottom: 30px; right: 30px; z-index: 2000">
    <v-menu :close-on-content-click="false" location="top end">
      <template v-slot:activator="{ props }">
        <v-btn
          v-bind="props"
          icon="mdi-robot-outline"
          color="secondary"
          @click="generateExplanation"></v-btn>
      </template>
      <v-card
        width="300"
        max-height="300"
        class="mb-1"
        title="LLM explanation"
        variant="outlined"
        color="secondary">
        <v-divider class="mx-4" thickness="4"></v-divider>
        <div v-if="isExplaining" class="d-flex flex-column align-center justify-center h-100 py-4">
          <v-progress-circular indeterminate color="secondary" size="30" />
        </div>
        <v-card-text v-if="!isExplaining" class="overflow-y-auto" style="white-space: pre-line">
          {{ props.showStr }}
        </v-card-text>
      </v-card>
    </v-menu>
  </div>
</template>
