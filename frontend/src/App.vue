<template>
  <div class="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
    <header class="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-4">
      <router-link to="/collections" class="text-lg font-semibold text-blue-400 hover:text-blue-300">
        uac2timeline
      </router-link>
      <nav class="flex gap-4 text-sm text-gray-400">
        <router-link to="/collections" class="hover:text-gray-100" active-class="text-gray-100">Collections</router-link>
        <router-link to="/tags" class="hover:text-gray-100" active-class="text-gray-100">Tags</router-link>
      </nav>
    </header>
    <main class="flex-1">
      <router-view />
    </main>
  </div>
</template>
