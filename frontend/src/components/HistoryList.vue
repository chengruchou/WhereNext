<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace, UserHistory } from "@/types/place"
  const props = defineProps<{ userHistory: UserHistory[] | null }>()
  const emit = defineEmits<{
    (e: "delete-all"): void
    (e: "delete-one", payload: { delId: number }): void
  }>()
  const deleteAll = async () => {
    emit("delete-all")
  }

  const deleteOne = async (id: number) => {
    emit("delete-one", { delId: id })
  }
</script>

<template>
  <v-card title="User History" variant="outlined" class="mx-4" color="secondary">
    <template #append>
      <v-btn v-if="props.userHistory?.length!==0" color="error" variant="tonal" size="small" @click="deleteAll"> Delete all </v-btn>
    </template>
    <v-card-text v-if="!props.userHistory || props.userHistory.length == 0">
      No history
    </v-card-text>
    <v-card-text>
      <v-list>
        <v-list-item v-for="(e, index) in props.userHistory" :key="index" class="my-2 border-b-md">
          <div>
            <v-list-item-title> # {{ index + 1 }} </v-list-item-title>
            <v-list-item-subtitle
              >{{ e.poi_detail?.raw_poi_id + " " + e.poi_detail?.category_name }}
            </v-list-item-subtitle>
            Visit time : {{ e.visit_time }}
          </div>
          <template #append>
            <v-btn
              color="error"
              variant="tonal"
              size="small"
              icon="mdi-delete"
              @click="deleteOne(e.log_id)" />
          </template>
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>
