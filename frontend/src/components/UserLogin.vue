<script lang="ts" setup>
  import { ref, onMounted, computed, watch } from "vue"
  import axios from "axios"
  const userId = ref("")
  const emit = defineEmits<{
    (e: "submit-user-id", payload: { passId: string }): void
  }>()
  watch(userId, () => {
    emit("submit-user-id", { passId: userId.value })
  })
</script>

<template>
  <v-card title="User Login" variant="outlined" class="ma-4" color="primary">
    <v-card-item title="">
      <v-text-field label="User Id" v-model="userId"> </v-text-field>
    </v-card-item>
  </v-card>
</template>
