<script setup lang="ts">
import {ref} from "vue"
const text=ref('')
</script>

<template>
  <div class="min-h-screen flex flex-col items-center justify-center gap-4 bg-gray-100">
    <h1 class="text-3xl font-bold text-blue-600">AI Chat</h1>
    <el-button type="primary">主按钮</el-button>
    <el-input v-model="text" placeholder="试试输入框" class="w-64" />
  </div>
</template>
