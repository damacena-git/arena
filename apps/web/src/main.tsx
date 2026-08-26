import React, { FormEvent, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Message = { role: 'assistant' | 'user'; text: string; transcription?: string }
type Config = { app_name: string; user_name?: string; environment: string; ai_provider: string; groq_configured: boolean; openrouter_configured: boolean; groq_model?: string; openrouter_model?: string; groq_transcription_model?: string }

function App() {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [recording, setRecording] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const audioChunks = useRef<Blob[]>([])
  const [view, setView] = useState<'chat' | 'settings' | 'clickup'>('chat')
  const [config, setConfig] = useState<Config | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', text: 'Olá! Eu sou a Sofia. Como posso ajudar você hoje?' },
  ])

  const [clickupConnected, setClickupConnected] = useState(false)
  const [clickupLists, setClickupLists] = useState<{ id: string; name: string }[]>([])
  const [clickupTasks, setClickupTasks] = useState<{ id: string; name: string; priority?: string }[]>([])
  const [clickupTaskName, setClickupTaskName] = useState('')
  const [clickupFormList, setClickupFormList] = useState('')
  const [clickupLoading, setClickupLoading] = useState(false)
  const [clickupError, setClickupError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/v1/config')
      .then((response) => response.json())
      .then(setConfig)
      .catch(() => undefined)
    refreshClickupStatus()
  }, [])

  async function refreshClickupStatus() {
    try {
      const response = await fetch('/api/v1/integrations/clickup/status')
      const data = await response.json()
      setClickupConnected(Boolean(data.connected))
      if (data.connected) {
        Promise.all([
          fetch('/api/v1/integrations/clickup/lists').then((response) => response.json()),
          fetch('/api/v1/integrations/clickup/tasks').then((response) => response.json()),
        ])
          .then(([listsResponse, tasksResponse]) => {
            setClickupLists((listsResponse.lists || []).slice(0, 50))
            setClickupTasks((tasksResponse.tasks || []).slice(0, 50))
            if (!clickupFormList && listsResponse.lists && listsResponse.lists[0]) {
              setClickupFormList(listsResponse.lists[0].id)
            }
          })
          .catch(() => {})
      }
    } catch {
      setClickupConnected(false)
    }
  }

  async function createClickupTask(event: FormEvent) {
    event.preventDefault()
    if (!clickupTaskName.trim()) return
    setClickupLoading(true)
    setClickupError(null)
    try {
      const listId = clickupFormList || new URLSearchParams(window.location.search).get('clickup_list') || undefined
      const body: Record<string, unknown> = { name: clickupTaskName }
      if (listId) body.list_id = listId
      const response = await fetch('/api/v1/integrations/clickup/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Não foi possível criar a tarefa.')
      setClickupTaskName('')
      const tasksResponse = listId
        ? await fetch(`/api/v1/integrations/clickup/tasks?list_id=${encodeURIComponent(listId)}`).then((response) => response.json())
        : await fetch('/api/v1/integrations/clickup/tasks').then((response) => response.json())
      setClickupTasks((tasksResponse.tasks || []).slice(0, 50))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Falha ao criar tarefa.'
      setClickupError(message)
    } finally {
      setClickupLoading(false)
    }
  }

  function speak(text: string) {
    if (!voiceEnabled || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'pt-BR'
    utterance.rate = 0.96
    utterance.pitch = 1.06
    const voices = window.speechSynthesis.getVoices()
    const feminineVoice = voices.find((voice) => /pt[-_]BR/i.test(voice.lang) && /female|feminina|maria|francisca|luciana|fernanda|google português|brasil/i.test(voice.name))
      || voices.find((voice) => /pt[-_]BR/i.test(voice.lang))
    if (feminineVoice) utterance.voice = feminineVoice
    window.speechSynthesis.speak(utterance)
  }

  async function sendAudio(file: Blob, filename: string) {
    setSending(true)
    const form = new FormData()
    form.append('file', file, filename)
    if (conversationId) form.append('conversation_id', conversationId)
    try {
      const response = await fetch('/api/v1/chat/audio', { method: 'POST', body: form })
      const data = await response.json()
      setConversationId(data.conversation_id)
      setMessages((current) => [...current, { role: 'user', text: `Áudio: ${filename}` }, { role: 'assistant', text: data.text, transcription: data.transcription }])
      speak(data.text)
    } catch {
      setMessages((current) => [...current, { role: 'assistant', text: 'Não consegui enviar o áudio para a API.' }])
    } finally { setSending(false) }
  }

  async function toggleRecording() {
    if (recording && mediaRecorder.current) {
      mediaRecorder.current.stop()
      setRecording(false)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      audioChunks.current = []
      recorder.ondataavailable = (event) => { if (event.data.size > 0) audioChunks.current.push(event.data) }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        const audio = new Blob(audioChunks.current, { type: 'audio/webm' })
        if (audio.size > 0) void sendAudio(audio, `gravacao-${Date.now()}.webm`)
      }
      mediaRecorder.current = recorder
      recorder.start()
      setRecording(true)
    } catch {
      setMessages((current) => [...current, { role: 'assistant', text: 'Não consegui acessar seu microfone. Verifique a permissão do navegador.' }])
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages((current) => [...current, { role: 'user', text }])
    setSending(true)
    try {
      const response = await fetch('/api/v1/chat/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, conversation_id: conversationId }) })
      const data = await response.json()
      setConversationId(data.conversation_id)
      setMessages((current) => [...current, { role: 'assistant', text: data.text }])
      speak(data.text)
    } catch {
      setMessages((current) => [...current, { role: 'assistant', text: 'Não consegui falar com a API. Verifique se o backend está ativo.' }])
    } finally { setSending(false) }
  }

  return <main className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">✦</span><span>Sofia</span></div>
      <p className="eyebrow">SECRETÁRIA PESSOAL</p>
      <nav>
        <button className={`nav-item ${view === 'chat' ? 'active' : ''}`} onClick={() => setView('chat')}>◌ <span>Conversa</span></button>
        <button className={`nav-item ${view === 'clickup' ? 'active' : ''}`} onClick={() => setView('clickup')}>✓ <span>Tarefas</span></button>
        <button className="nav-item">◷ <span>Agenda</span></button>
        <button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>⚙ <span>Configuração</span></button>
      </nav>
      <div className="status"><span className="dot" /> Sistema online<br /><small>Modo de desenvolvimento</small></div>
    </aside>
    <section className="content">
      {view === 'clickup' ? <ClickupPanel
        connected={clickupConnected}
        lists={clickupLists}
        tasks={clickupTasks}
        statusLabel={clickupLoading ? 'Salvando' : clickupError ? 'Falha' : 'Atualizado'}
        taskName={clickupTaskName}
        setTaskName={setClickupTaskName}
        selectedList={clickupFormList}
        setSelectedList={setClickupFormList}
        onCreate={createClickupTask}
        error={clickupError}
      /> : view === 'settings' ? <Settings config={config} clickupConnected={clickupConnected} /> : <>
        <header className="topbar"><div><p className="eyebrow">CENTRAL DE COMANDO</p><h1>Bom dia, {config?.user_name || 'Diego'}</h1></div><div className="avatar">E</div></header>
        <div className="conversation">
          <div className="welcome"><div className="orb">✦</div><h2>Em que posso ajudar?</h2><p>Peça para organizar suas tarefas, notas e compromissos.</p><div className="suggestions"><button onClick={() => setInput('O que tenho para fazer hoje?')}>O que tenho para fazer hoje?</button><button onClick={() => setInput('Crie uma tarefa no ClickUp')}>Criar tarefa no ClickUp</button><button onClick={() => setInput('Salve uma nota no Notion')}>Salvar nota no Notion</button></div></div>
          <div className="messages">{messages.map((message, index) => <div key={index} className={`message ${message.role}`}><span>{message.transcription && <small className="transcription">Transcrição: {message.transcription}</small>}{message.text}</span></div>)}</div>
        </div>
        <form className="composer" onSubmit={sendMessage}><button type="button" className={`voice-button ${voiceEnabled ? 'enabled' : ''}`} onClick={() => setVoiceEnabled((enabled) => !enabled)} title="Ativar ou silenciar respostas faladas">{voiceEnabled ? '🔊 Voz' : '🔇 Voz'}</button><button type="button" className={`record-button ${recording ? 'recording' : ''}`} onClick={toggleRecording} disabled={sending}>{recording ? '■ Parar' : '● Gravar'}</button><label className="audio-button" title="Enviar arquivo de áudio">↥ Arquivo<input type="file" accept="audio/*,.mp3,.wav,.m4a,.ogg,.webm" hidden onChange={(e) => { const file = e.target.files?.[0]; if (file) void sendAudio(file, file.name); e.currentTarget.value = '' }} /></label><input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Fale com a Sofia..." aria-label="Mensagem"/><button disabled={sending || !input.trim()}>{sending ? '…' : 'Enviar'} <span>↗</span></button></form>
        <p className="hint">Clique em <strong>● Gravar</strong> para falar e receba a resposta em áudio. <strong>🔊 Voz</strong> liga/desliga a fala.</p>
      </>}
    </section>
  </main>
}

function ClickupPanel({ connected, lists, tasks, statusLabel, taskName, setTaskName, selectedList, setSelectedList, onCreate, error }: { connected: boolean; lists: { id: string; name: string }[]; tasks: { id: string; name: string; priority?: string }[]; statusLabel: string; taskName: string; setTaskName: (value: string) => void; selectedList: string; setSelectedList: (value: string) => void; onCreate: (event: FormEvent) => void; error: string | null }) {
  return <div className="settings-page"><p className="eyebrow">CLICKUP</p><h1>Tarefas</h1><p className="settings-lead">Gerencie suas listas e tarefas do ClickUp direto pela Sofia.</p><div className="settings-card"><div className="integration-row"><div><strong>Status da conexão</strong><small>{connected ? 'Conectado.' : 'Sem conexão ativa.'}</small></div><span className={`status-pill ${connected ? 'ok' : 'muted'}`}>{statusLabel}</span></div>{!connected ? <p className="settings-note">Adicione <strong>CLICKUP_API_KEY</strong> e <strong>CLICKUP_DEFAULT_TEAM_ID</strong> no .env para liberar essa tela.</p> : <><form className="composer" onSubmit={onCreate}><input value={taskName} onChange={(event) => setTaskName(event.target.value)} placeholder="Nova tarefa" /><select value={selectedList} onChange={(event) => setSelectedList(event.target.value)}>{lists.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="submit" disabled={!taskName.trim()}>{statusLabel === 'Salvando' ? 'Salvando…' : 'Criar'}</button></form>{error && <p className="settings-note" style={{ color: '#f87171' }}>{error}</p>}<div className="task-list">{tasks.length ? tasks.map((item) => <div key={item.id} className="task-card"><strong>{item.name}</strong><small>{item.priority || ''}</small></div>) : <p className="settings-note">Nenhuma tarefa encontrada.</p>}</div></>}</div></div>
}

function Settings({ config, clickupConnected }: { config: Config | null; clickupConnected: boolean }) {
  return <div className="settings-page"><p className="eyebrow">CONFIGURAÇÃO</p><h1>Inteligência da Sofia</h1><p className="settings-lead">Informações técnicas disponíveis apenas nesta área de administração.</p><div className="settings-card"><div className="integration-row"><div><strong>Google Calendar</strong><small>Conecte sua agenda para consultar compromissos.</small></div><a className="connect-button" href="/api/v1/integrations/google/start">Conectar agenda</a></div><div className="integration-row"><div><strong>ClickUp</strong><small>Integração com listas e tarefas.</small></div><span className={`status-pill ${clickupConnected ? 'ok' : 'muted'}`}>{clickupConnected ? 'Conectado' : 'Desconectado'}</span></div><div className="setting-row"><span>Usuário</span><strong>{config?.user_name || 'Diego'}</strong></div><div className="setting-row"><span>Provedor principal</span><strong>{config?.ai_provider || 'Carregando…'}</strong></div><div className="setting-row"><span>Groq</span><strong className={config?.groq_configured ? 'ok' : 'muted'}>{config?.groq_configured ? 'Configurado' : 'Não configurado'}</strong></div><div className="setting-row"><span>OpenRouter</span><strong className={config?.openrouter_configured ? 'ok' : 'muted'}>{config?.openrouter_configured ? 'Configurado' : 'Não configurado'}</strong></div><div className="setting-row"><span>Modelo de conversa Groq</span><strong>{config?.groq_model || 'llama-3.3-70b-versatile'}</strong></div><div className="setting-row"><span>Modelo de transcrição</span><strong>{config?.groq_transcription_model || 'whisper-large-v3-turbo'}</strong></div><div className="setting-row"><span>Ambiente</span><strong>{config?.environment || 'development'}</strong></div></div><p className="settings-note">As chaves permanecem somente no backend e nunca são exibidas.</p></div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
