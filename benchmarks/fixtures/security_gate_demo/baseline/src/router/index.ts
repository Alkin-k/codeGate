import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { public: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/app',
    name: 'App',
    component: () => import('../views/App.vue'),
    children: [
      {
        path: 'workspace',
        name: 'Workspace',
        component: () => import('../views/Workspace.vue'),
        meta: { title: '工作台' }
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('../views/Settings.vue')
      },
      {
        path: 'membership',
        name: 'Membership',
        component: () => import('../views/Membership.vue'),
        meta: { title: '会员中心' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
  const token = await getToken()
  const isPublic = Boolean(to.meta?.public)
  if (!isPublic && !token) {
    return { name: 'Login' }
  }
})

async function getToken(): Promise<string | null> {
  return localStorage.getItem('auth_token')
}

export default router
