<script lang="ts" setup>
  import { ref } from "vue"
  
  const userId = ref<number | null>(null)
  const isLoggedIn = ref(false)
  const formRef = ref<any>(null) // Reference to the form

  const emit = defineEmits<{
    (e: "submit-user-id", payload: { passUserId: number | null }): void
  }>()

  // Array of validation rules
  const idRules = [
    (value: any) => !!value || 'User ID is required.',
    (value: any) => Number.isInteger(Number(value)) || 'User ID must be a number.'
  ]

  const toggleLogin = async () => {
    if (isLoggedIn.value) {
      // --- LOGOUT LOGIC ---
      isLoggedIn.value = false
      userId.value = null // Optional: clear the field upon logout
      emit("submit-user-id", { passUserId: null })
      
      // Reset the form validation state so errors disappear on logout
      if (formRef.value) formRef.value.resetValidation() 
    } else {
      // --- LOGIN LOGIC ---
      // Trigger Vuetify's validation check
      const { valid } = await formRef.value.validate()
      
      if (!valid) return // Stop execution if the field is empty or invalid
      
      isLoggedIn.value = true
      emit("submit-user-id", { passUserId: userId.value })
    }
  }
</script>

<template>
  <v-card title="User Login" variant="outlined" class="ma-4" color="primary">
    <v-card-text>
      <v-form ref="formRef" @submit.prevent="toggleLogin">
        <div class="d-flex align-start ga-2">
          <v-text-field 
            density="compact"  
            label="User ID" 
            v-model.number="userId" 
            :readonly="isLoggedIn"
            :disabled="isLoggedIn"
            :rules="idRules"
            validate-on="submit"
            hide-details="auto"
          ></v-text-field>
          
          <v-btn 
            type="submit"
            :text="isLoggedIn ? 'Logout' : 'Login'" 
            :color="isLoggedIn ? 'error' : 'primary'" 
            width="10%"
          />
        </div>
      </v-form>
    </v-card-text>
  </v-card>
</template>