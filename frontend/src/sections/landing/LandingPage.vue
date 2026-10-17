<template>
  <v-app-bar height="68" color="surface" class="soft-bar">
    <RouterLink class="brand" to="/" aria-label="AgroLogistix, на главную">
      <v-icon icon="mdi-sprout-outline" color="primary" size="24" />
      <span>AgroLogistix</span>
    </RouterLink>
  </v-app-bar>

  <v-main class="d-flex align-center justify-center pa-6">
    <div class="hero">
      <h1 class="hero-title">Планирование поставок урожая</h1>
      <p class="hero-text">
        Сервис соберёт заказы покупателей, остатки на складах и машины в маршруты, посчитает
        сохранность груза и затраты на доставку.
      </p>
      <v-btn to="/login" color="accent" size="large" class="btn-gradient" min-width="200"
        >Войти</v-btn
      >
    </div>
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

.hero {
  display: grid;
  justify-items: center;
  gap: 12px;
  max-width: 520px;
  text-align: center;
}

.hero-title {
  margin: 0;
  font-size: 28px;
  line-height: 1.15;
}

.hero-text {
  margin: 0 0 8px;
  font-size: 15px;
  color: #5b5175;
}
</style>
