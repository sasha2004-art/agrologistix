<template>
  <v-app>
    <RouterView />
    <NotificationHost />
  </v-app>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
import NotificationHost from '@/shared/components/NotificationHost.vue'
</script>
