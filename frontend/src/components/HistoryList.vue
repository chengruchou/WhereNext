<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { PlaceInfo } from "@/types/place";
  const userId = ref("")
  const props = defineProps<{ userHistory: PlaceInfo[] | undefined }>()
</script>

<template>
  <v-card title="User History" variant="outlined" class="mx-4" color="secondary">
    <v-card-text v-if="!props.userHistory || props.userHistory.length == 0">
      No history
    </v-card-text>
    <v-card-text>
      <v-list>
        <v-list-item v-for="(e, index) in props.userHistory" :key="index">
          <v-list-item-title> # {{ index + 1 }} </v-list-item-title>
          <v-list-item-subtitle> Site Name : {{ e.name }} </v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>
