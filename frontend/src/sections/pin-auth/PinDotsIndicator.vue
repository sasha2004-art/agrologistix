<template>
  <div class="pin-dots" :class="{ 'pin-dots--error': error, 'pin-dots--shake': shaking }" role="group" aria-label="Введено цифр PIN-кода">
    <span
      v-for="index in 6"
      :key="index"
      class="pin-dot"
      :class="{ 'pin-dot--filled': index <= length }"
      :aria-label="index <= length ? 'Цифра введена' : 'Пусто'"
    />
  </div>
</template>

<script setup lang="ts">
defineProps<{ length: number; error: boolean; shaking: boolean }>()
</script>

<style scoped lang="scss">
.pin-dots { display: flex; justify-content: center; gap: 17px; }
.pin-dot { width: 13px; height: 13px; border: 1px solid rgba(226,232,240,.58); border-radius: 50%; background: rgba(15,23,42,.2); transition: background .16s ease, border-color .16s ease, transform .16s ease; }
.pin-dot--filled { transform: scale(1.08); border-color: #6ee7b7; background: #10b981; box-shadow: 0 0 14px rgba(16,185,129,.35); }
.pin-dots--error .pin-dot { border-color: #ef4444; background: rgba(239,68,68,.78); box-shadow: 0 0 12px rgba(239,68,68,.28); }
.pin-dots--shake { animation: shake 300ms ease both; }
@keyframes shake { 0%, 100% { transform: translateX(0); } 20%, 60% { transform: translateX(-8px); } 40%, 80% { transform: translateX(8px); } }
@media (prefers-reduced-motion: reduce) { .pin-dots--shake { animation: none; } }
</style>
