<template>
  <v-app-bar height="64" color="surface" class="soft-bar">
    <RouterLink class="brand" to="/" aria-label="AgroLogistix, главная">
      <v-icon icon="mdi-leaf" color="primary" />
      <span>AgroLogistix</span>
    </RouterLink>
    <v-spacer />
    <v-btn to="/login" color="primary" class="btn-gradient">Терминал логиста</v-btn>
  </v-app-bar>

  <v-main>
    <v-container max-width="1040" class="py-10 py-md-16">
      <section class="hero" aria-labelledby="hero-title">
        <p class="hero-kicker">Био-логистика · Калужская область</p>
        <h1 id="hero-title" class="text-h4 text-md-h3 font-weight-regular">Свежий урожай вовремя</h1>
        <p class="hero-text">
          AgroLogistix планирует поставки скоропортящегося урожая из складов Обнинска
          в B2B-точки Калужской области и считает экономику каждого рейса.
        </p>
        <v-btn to="/login" color="primary" size="large" class="btn-gradient">Открыть терминал</v-btn>
      </section>

      <v-row class="mt-8 mt-md-12">
        <v-col v-for="capability in capabilities" :key="capability.title" cols="12" md="4">
          <v-card class="soft-card h-100">
            <v-card-item>
              <template #prepend>
                <v-icon :icon="capability.icon" color="primary" size="22" />
              </template>
              <v-card-title class="text-body-1 font-weight-medium">{{ capability.title }}</v-card-title>
            </v-card-item>
            <v-card-text class="text-body-2 text-medium-emphasis">{{ capability.text }}</v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </v-container>

    <v-footer class="soft-footer justify-center">
      <span class="text-caption text-medium-emphasis">© AgroLogistix · Калуга — Обнинск</span>
    </v-footer>
  </v-main>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'

interface Capability {
  icon: string
  title: string
  text: string
}

const capabilities: Capability[] = [
  {
    icon: 'mdi-thermometer-lines',
    title: 'Свежесть груза',
    text: 'Расчёт ожидаемой свежести E[Freshness] с учётом температуры, осадков и рефрижератора.',
  },
  {
    icon: 'mdi-truck-fast-outline',
    title: 'Маршруты и автопарк',
    text: 'Учёт вместимости машин, типа дороги и состояния транспорта при распределении партий.',
  },
  {
    icon: 'mdi-chart-line',
    title: 'Экономика рейса',
    text: 'Полный TCO: стоимость рейсов, потери от порчи урожая и штрафы за недовоз.',
  },
]
</script>

<style scoped lang="scss">
.brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-inline-start: 12px;
  color: inherit;
  text-decoration: none;
  font-size: 16px;
  font-weight: 600;
}

.hero {
  max-width: 620px;
}

.hero-kicker {
  margin: 0 0 10px;
  color: rgb(var(--v-theme-primary-darken-1));
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-text {
  margin: 14px 0 26px;
  color: rgba(43, 42, 38, 0.72);
  font-size: 16px;
  line-height: 1.6;
}

h1 {
  letter-spacing: -0.01em;
}
</style>
