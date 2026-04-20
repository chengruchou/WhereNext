<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import type { GowallaPlace, UserHistory } from "@/types/place"
  const props = defineProps<{ userHistory: UserHistory[] | null }>()
  const emit = defineEmits<{
    (e: "delete-all"): void
    (e: "delete-one", payload: { delId: number }): void
    (e: "focus-place", payload: { focusPlace: GowallaPlace | null }): void
  }>()
  const deleteAll = async () => {
    emit("delete-all")
  }

  const deleteOne = async (id: number) => {
    emit("delete-one", { delId: id })
  }
  const formatTime = (isoString: string | null) => {
    if (!isoString) return ''
    const date = new Date(isoString)
    // Formats to "Apr 19, 10:51 AM"
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    })
  }
</script>

<template>
  <v-card title="User History" variant="outlined" class="mx-4" color="secondary">
    
    <template #append>
      <v-tooltip text="Delete All History" location="top">
        <template v-slot:activator="{ props: tooltipProps }">
          <v-btn 
            v-if="props.userHistory && props.userHistory.length !== 0" 
            v-bind="tooltipProps"
            class="flex-shrink-0" 
            color="error" 
            variant="tonal" 
            size="small"
            icon="mdi-delete-sweep" 
            @click="deleteAll"
          />
        </template>
      </v-tooltip>
    </template>

    <v-card-text v-if="!props.userHistory || props.userHistory.length === 0">
      No history
    </v-card-text>

    <v-card-text v-else style="height: 250px; overflow-y: auto;" class="pa-3">
      <v-list class="bg-transparent pa-0">
        <v-list-item v-for="(e, index) in props.userHistory" :key="index" class="my-2 border-b-md px-0" @click="emit('focus-place', { focusPlace: e.poi_detail })">
          
          <div class="flex-grow-1 text-wrap text-caption pr-2">
            <div class="text-body-1 font-weight-bold mb-1">
              # {{ index + 1 }}
              <v-chip size="small" variant="tonal" color="secondary" class="ml-3">
                ID: {{ e.poi_detail?.raw_poi_id }}
              </v-chip>
            </div>
            
            <v-tooltip :text="e.poi_detail?.raw_poi_id + ' ' + e.poi_detail?.category_name" location="top">
              <template v-slot:activator="{ props: tooltipProps }">
                <div v-bind="tooltipProps" class="text-wrap text-body-2 mb-1" style="cursor: default;">
                  {{ e.poi_detail?.category_name }}
                </div>
              </template>
            </v-tooltip>

            <div class="text-grey">{{ formatTime(e.visit_time) }}</div>
          </div>

          <template #append>
            <v-btn
              color="error"
              variant="tonal"
              size="small"
              icon="mdi-delete"
              class="flex-shrink-0"
              @click="deleteOne(e.log_id)" 
            />
          </template>
          
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>