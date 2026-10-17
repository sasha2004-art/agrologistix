<template>
  <v-app>
    <RouterView />
    <NotificationHost />
    <PrintableRouteSheet />
  </v-app>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
import NotificationHost from '@/shared/components/NotificationHost.vue'
import PrintableRouteSheet from '@/sections/erp-dashboard/PrintableRouteSheet.vue'
</script>
