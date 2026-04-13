<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace, UserHistory } from "@/types/place"
  const userId = ref("")
  const props = defineProps<{ userHistory: UserHistory[] | null }>()
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
          <v-list-item-subtitle> Site Id : {{ e.poi_detail?.raw_poi_id }} </v-list-item-subtitle>
          Visit time : {{ e.visit_time }}
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>
