<template>
  <div class="video-scene" aria-hidden="true">
    <video autoplay loop muted playsinline preload="metadata" :src="videoUrl" />
  </div>
</template>

<script setup lang="ts">
const videoUrl =
  'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260429_114316_1c7889ad-2885-410e-b493-98119fee0ddb.mp4'
</script>
