import {createRouter,createWebHistory} from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = createRouter({
    history:createWebHistory(
        import.meta.env.BASE_URL
    ),
    routes: [
    {
        path:'/',
        redirect:'/home',
    },
    {
      path: '/login',
      component: () => import('@/views/Login.vue'),
    },

    {
      path: '/home',
      component: () => import('@/views/Home.vue'),
      meta: {
        requiresAuth: true,
      },
    },

    {
      path: '/chat',
      component: () => import('@/views/Chat.vue'),
      meta: {
        requiresAuth: true,
      },
    },
  ],
})

router.beforeEach((to) => {
  const userStore = useUserStore()

  // ① 需要登录的页面
  if (to.meta.requiresAuth && !userStore.isLogin) {
    return '/login'
  }

  // ② 已经登录，却访问登录页
  if (to.path === '/login' && userStore.isLogin) {
    return '/home'
  }

  // ③ 其他情况正常放行
  return true
})
export default router