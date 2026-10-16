<template>
  <v-app-bar height="68" color="surface" class="soft-bar">
    <RouterLink class="brand" to="/" aria-label="Serenity, на главную">
      <v-icon icon="mdi-spa-outline" color="primary" size="24" />
      <span>Serenity</span>
    </RouterLink>
  </v-app-bar>

  <v-main class="d-flex align-center justify-center pa-6">
    <v-btn to="/login" color="accent" size="large" class="btn-gradient" min-width="200"
      >Войти</v-btn
    >
  </v-main>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<style scoped lang="scss">
.brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-inline-start: 12px;
  color: inherit;
  text-decoration: none;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 600;
}
</style>
