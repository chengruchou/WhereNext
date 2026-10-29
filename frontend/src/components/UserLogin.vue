<script lang="ts" setup>
  import { computed, ref, watch } from "vue"

  // The traveler loaded in the app, which a demo traveler can set from outside.
  const props = defineProps<{ currentId: number | null }>()

  const userId = ref<number | null>(null)
  const isLoggedIn = ref(false)
  const formRef = ref<any>(null)

  const emit = defineEmits<{
    (e: "submit-user-id", payload: { passUserId: number | null }): void
  }>()

  watch(
    () => props.currentId,
    (id) => {
      userId.value = id
      isLoggedIn.value = id != null
    },
    { immediate: true },
  )

  const idRules = [
    (value: number | string | null) =>
      (value !== null && value !== "") || "User ID is required.",
    (value: number | string | null) =>
      Number.isInteger(Number(value)) || "User ID must be an integer.",
  ]

  const actionLabel = computed(() => isLoggedIn.value ? "Change" : "Load")

  const toggleLogin = async () => {
    if (isLoggedIn.value) {
      isLoggedIn.value = false
      userId.value = null
      emit("submit-user-id", { passUserId: null })
      
      if (formRef.value) formRef.value.resetValidation() 
    } else {
      const { valid } = await formRef.value.validate()
      
      if (!valid) return
      
      isLoggedIn.value = true
      emit("submit-user-id", { passUserId: userId.value })
    }
  }
</script>

<template>
  <v-form ref="formRef" class="user-login" @submit.prevent="toggleLogin">
    <v-text-field
      density="compact"
      label="User ID"
      v-model.number="userId"
      :readonly="isLoggedIn"
      :disabled="isLoggedIn"
      :rules="idRules"
      validate-on="submit"
      hide-details="auto"
      prepend-inner-icon="mdi-account-search-outline"
      variant="outlined"
    ></v-text-field>

    <v-btn
      type="submit"
      :text="actionLabel"
      :color="isLoggedIn ? undefined : 'primary'"
      :variant="isLoggedIn ? 'outlined' : 'flat'"
      class="user-login__action"
    />
  </v-form>
</template>

<style scoped>
  .user-login {
    align-items: flex-start;
    display: grid;
    gap: 10px;
    grid-template-columns: minmax(0, 1fr) 92px;
  }

  .user-login__action {
    font-weight: 500;
    height: 40px;
    letter-spacing: 0;
    min-width: 0;
    text-transform: none;
  }

  @media (max-width: 720px) {
    .user-login {
      grid-template-columns: 1fr;
    }

    .user-login__action {
      width: 100%;
    }
  }
</style>
