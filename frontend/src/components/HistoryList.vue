<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace, UserHistory } from "@/types/place"
  const props = defineProps<{ userHistory: UserHistory[] | null }>()
  const emit = defineEmits<{ (e: "handle-delete"): void }>()
  const handleDelete = async () => {
    emit("handle-delete")
  }
</script>

<template>
  <v-card title="User History" variant="outlined" class="mx-4" color="secondary">
    <template #append>
      <v-btn color="error" icon="mdi-delete" variant="tonal" size="small" @click="handleDelete" />
    </template>
    <v-card-text v-if="!props.userHistory || props.userHistory.length == 0">
      No history
    </v-card-text>
    <v-card-text>
      <v-list>
        <v-list-item v-for="(e, index) in props.userHistory" :key="index">
          <v-list-item-title> # {{ index + 1 }} </v-list-item-title>
          <v-list-item-subtitle
            >{{ e.poi_detail?.raw_poi_id + " " + e.poi_detail?.category_name }}
          </v-list-item-subtitle>
          Visit time : {{ e.visit_time }}
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>
