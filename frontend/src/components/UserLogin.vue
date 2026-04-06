<script lang="ts" setup>
import { ref, onMounted, computed, watch } from "vue";
import axios from "axios";
const userId = ref('');
const emit = defineEmits<{
  (e: 'submit-userId', payload: { passId: string }): void
}>()
watch(userId, () => {
  emit("submit-userId", {passId: userId.value})
})
</script>

<template>
  <v-card title="User Login">
    <v-card-item title="">
      <v-text-field label="User Id" v-model="userId"> </v-text-field>
    </v-card-item>
  </v-card>
</template>
