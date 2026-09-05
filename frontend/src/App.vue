<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <ShieldCheckIcon :size="28" />
        <div>
          <h1>Enterprise Knowledge Assistant</h1>
          <p>Personal Demo</p>
        </div>
      </div>

      <label class="field">
        <span>Demo user selector</span>
        <select v-model="selectedUserId">
          <option v-for="user in users" :key="user.id" :value="user.id">
            {{ user.display_name }}
          </option>
        </select>
        <small class="helper-text">Simulated identity for portfolio access-control checks, not real authentication.</small>
      </label>

      <div class="mode-card">
        <strong>{{ aiModeLabel }}</strong>
        <span>{{ aiStatusText }}</span>
      </div>

      <nav class="nav-tabs">
        <button :class="{ active: tab === 'chat' }" @click="tab = 'chat'">
          <MessageSquareIcon :size="18" /> Chat
        </button>
        <button :class="{ active: tab === 'documents' }" @click="tab = 'documents'">
          <BookOpenIcon :size="18" /> Documents
        </button>
        <button :class="{ active: tab === 'evaluation' }" @click="tab = 'evaluation'">
          <ActivityIcon :size="18" /> Evaluation
        </button>
      </nav>
    </aside>

    <main class="workspace">
      <section v-if="tab === 'chat'" class="panel chat-panel">
        <header class="panel-header">
          <div>
            <h2>Ask internal knowledge</h2>
            <p>Answers are limited to documents visible to the selected demo user.</p>
          </div>
        </header>

        <form class="ask-box" @submit.prevent="ask">
          <textarea v-model="question" placeholder="Ask about vacation policy, incident escalation, or Project Orion..." />
          <button :disabled="loading || !question.trim()">
            <MessageSquareIcon :size="18" /> Ask
          </button>
        </form>

        <div v-if="answer" class="answer-layout">
          <article class="answer">
            <span class="status" :class="answer.status">{{ answer.status.replace('_', ' ') }}</span>
            <p>{{ answer.answer }}</p>
            <small>{{ answer.latency_ms }} ms</small>
          </article>

          <section class="sources">
            <h3>Citations</h3>
            <article v-for="citation in answer.citations" :key="citation.chunk_id" class="source-card">
              <strong>{{ citation.document_title }}</strong>
              <span>Page {{ citation.page || 'n/a' }} · Version {{ citation.version }}</span>
              <p>{{ citation.excerpt }}</p>
            </article>
            <p v-if="!answer.citations.length" class="empty">No citations were returned.</p>
          </section>
        </div>
      </section>

      <section v-if="tab === 'documents'" class="panel">
        <header class="panel-header">
          <div>
            <h2>Document management</h2>
            <p>Upload source material and assign access controls as the selected simulated user.</p>
          </div>
        </header>

        <form class="upload-form" @submit.prevent="upload">
          <label class="field">
            <span>Title</span>
            <input v-model="uploadForm.title" required />
          </label>
          <label class="field">
            <span>Department</span>
            <input v-model="uploadForm.department" required />
          </label>
          <label class="field">
            <span>Roles</span>
            <input v-model="uploadForm.roles" placeholder="employee,hr" required />
          </label>
          <label class="field">
            <span>Classification</span>
            <select v-model="uploadForm.classification">
              <option value="public">Public</option>
              <option value="internal">Internal</option>
              <option value="confidential">Confidential</option>
            </select>
          </label>
          <label class="file-field">
            <UploadIcon :size="18" />
            <span>{{ uploadForm.file?.name || 'Choose PDF, DOCX, TXT, or Markdown' }}</span>
            <input type="file" accept=".pdf,.docx,.txt,.md,.markdown" @change="selectFile" />
          </label>
          <button :disabled="!uploadForm.file || !isAdmin"><FilePlusIcon :size="18" /> Upload</button>
        </form>
        <p v-if="!isAdmin" class="empty">Document upload, update, and delete require the Knowledge Admin demo user.</p>

        <div class="document-grid">
          <article v-for="document in documents" :key="document.id" class="document-card">
            <h3>{{ document.title }}</h3>
            <p>{{ document.department }}</p>
            <span>{{ document.roles.join(', ') }}</span>
            <span class="classification">{{ document.classification }}</span>
            <small>Version {{ document.version }} · {{ document.chunk_count }} chunks</small>
            <button class="danger-button" :disabled="!isAdmin" @click="removeDocument(document.id)">Delete</button>
          </article>
        </div>
      </section>

      <section v-if="tab === 'evaluation'" class="panel">
        <header class="panel-header">
          <div>
            <h2>Retrieval evaluation</h2>
            <p>Run the seeded quality checks and review recent query logs.</p>
          </div>
          <button @click="runEvaluation"><PlayIcon :size="18" /> Run</button>
        </header>

        <div v-if="evaluationSummary" class="metric-row">
          <div><strong>{{ evaluationSummary.hit_rate }}</strong><span>Hit rate</span></div>
          <div><strong>{{ evaluationSummary.mrr }}</strong><span>MRR</span></div>
          <div><strong>{{ evaluationSummary.citation_coverage }}</strong><span>Citation coverage</span></div>
        </div>

        <div class="logs">
          <article v-for="log in logs" :key="log.id">
            <strong>{{ log.question }}</strong>
            <span>{{ log.user_id }} · {{ log.status }} · {{ log.latency_ms }} ms</span>
            <p>{{ log.answer }}</p>
          </article>
          <p v-if="!logs.length" class="empty">No query logs yet.</p>
        </div>
      </section>

      <p v-if="error" class="toast">{{ error }}</p>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  ActivityIcon,
  BookOpenIcon,
  FilePlusIcon,
  MessageSquareIcon,
  PlayIcon,
  ShieldCheckIcon,
  UploadIcon,
} from '@lucide/vue'
import { api } from './api'

const tab = ref('chat')
const users = ref([])
const documents = ref([])
const logs = ref([])
const selectedUserId = ref('hr_user')
const question = ref('How many days in advance should employees request planned vacation?')
const answer = ref(null)
const error = ref('')
const loading = ref(false)
const evaluationSummary = ref(null)
const aiStatus = ref(null)

const uploadForm = reactive({
  title: '',
  department: 'General',
  roles: 'employee',
  classification: 'internal',
  file: null,
})

const selectedUser = computed(() => users.value.find((user) => user.id === selectedUserId.value))
const isAdmin = computed(() => selectedUser.value?.roles?.includes('admin'))
const aiModeLabel = computed(() => {
  if (!aiStatus.value?.embedding_configured && !aiStatus.value?.chat_configured) return 'Local fallback mode'
  if (aiStatus.value?.embedding_verified || aiStatus.value?.chat_verified) return 'OpenAI verified'
  return 'OpenAI configured, not verified'
})
const aiStatusText = computed(() => {
  if (!aiStatus.value) return 'Checking runtime mode...'
  if (!aiStatus.value.embedding_configured && !aiStatus.value.chat_configured) {
    return 'No API key configured; using local hash embeddings and extractive answers.'
  }
  return `Embeddings: ${aiStatus.value.embedding_mode}; chat: ${aiStatus.value.chat_mode}.`
})

async function loadAll() {
  users.value = await api.users()
  aiStatus.value = await api.aiStatus()
  await refreshUserScopedData()
  if (selectedUser.value === undefined && users.value.length) {
    selectedUserId.value = users.value[0].id
  }
}

async function refreshUserScopedData() {
  documents.value = await api.documents(selectedUserId.value)
  logs.value = await api.logs(selectedUserId.value)
}

async function ask() {
  error.value = ''
  loading.value = true
  try {
    answer.value = await api.chat({ question: question.value, user_id: selectedUserId.value })
    aiStatus.value = await api.aiStatus()
    logs.value = await api.logs(selectedUserId.value)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function selectFile(event) {
  uploadForm.file = event.target.files[0]
  if (!uploadForm.title && uploadForm.file) {
    uploadForm.title = uploadForm.file.name.replace(/\.[^.]+$/, '')
  }
}

async function upload() {
  error.value = ''
  try {
    await api.uploadDocument(uploadForm, selectedUserId.value)
    uploadForm.title = ''
    uploadForm.department = 'General'
    uploadForm.roles = 'employee'
    uploadForm.classification = 'internal'
    uploadForm.file = null
    aiStatus.value = await api.aiStatus()
    documents.value = await api.documents(selectedUserId.value)
  } catch (err) {
    error.value = err.message
  }
}

async function removeDocument(documentId) {
  error.value = ''
  try {
    await api.deleteDocument(documentId, selectedUserId.value)
    documents.value = await api.documents(selectedUserId.value)
  } catch (err) {
    error.value = err.message
  }
}

async function runEvaluation() {
  error.value = ''
  try {
    evaluationSummary.value = await api.runEvaluation()
    logs.value = await api.logs(selectedUserId.value)
  } catch (err) {
    error.value = err.message
  }
}

watch(selectedUserId, () => {
  refreshUserScopedData().catch((err) => {
    error.value = err.message
  })
})

onMounted(loadAll)
</script>
