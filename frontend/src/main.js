import { createApp } from 'vue'
import {
  Activity,
  BookOpen,
  FilePlus,
  MessageSquare,
  Play,
  ShieldCheck,
  Upload,
} from '@lucide/vue'
import './styles.css'
import App from './App.vue'

const app = createApp(App)
app.component('ActivityIcon', Activity)
app.component('BookOpenIcon', BookOpen)
app.component('FilePlusIcon', FilePlus)
app.component('MessageSquareIcon', MessageSquare)
app.component('PlayIcon', Play)
app.component('ShieldCheckIcon', ShieldCheck)
app.component('UploadIcon', Upload)
app.mount('#app')
