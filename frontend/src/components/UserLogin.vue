<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import axios from "axios"
  const userId = ref<number | null>(null)
  const emit = defineEmits<{
    (e: "submit-user-id", payload: { passUserId: number | null }): void
  }>()
  watch(userId, () => {
    emit("submit-user-id", { passUserId: userId.value })
  })
</script>

<template>
  <v-card title="User Login" variant="outlined" class="ma-4" color="primary">
    <v-card-text>
      <v-text-field label="User Id" v-model.number="userId" hide-details> </v-text-field>
    </v-card-text>
  </v-card>
</template>
