import { createRouter, createWebHistory } from 'vue-router'
import CollectionsView from '../views/CollectionsView.vue'
import AnalysisView from '../views/AnalysisView.vue'
import TagsView from '../views/TagsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/collections' },
    { path: '/collections', component: CollectionsView },
    { path: '/analysis/:id', component: AnalysisView, props: true },
    { path: '/tags', component: TagsView },
  ],
})
