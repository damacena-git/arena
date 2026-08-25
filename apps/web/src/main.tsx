import React, { FormEvent, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Message = { role: 'assistant' | 'user'; text: string; transcription?: string }
type Config = { app_name: string; environment: string; ai_provider: string; groq_configured: boolean; openrouter_configured: boolean; groq_model?: string; openrouter_model?: string; groq_transcription_model?: string }

function App() {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [view, setView] = useState<'chat' | 'settings'>('chat')
  const [config, setConfig] = useState<Config | null>(null)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', text: 'Olá! Eu sou a Sofia. Como posso ajudar você hoje?' },
  ])

  useEffect(() => { fetch('/api/v1/config').then((response) => response.json()).then(setConfig).catch(() => undefined) }, [])

  async function sendAudio(file: File) {
    setSending(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const response = await fetch('/api/v1/chat/audio', { method: 'POST', body: form })
      const data = await response.json()
      setMessages((current) => [...current, { role: 'user', text: `Áudio: ${file.name}` }, { role: 'assistant', text: data.text, transcription: data.transcription }])
    } catch {
      setMessages((current) => [...current, { role: 'assistant', text: 'Não consegui enviar o áudio para a API.' }])
    } finally { setSending(false) }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages((current) => [...current, { role: 'user', text }])
    setSending(true)
    try {
      const response = await fetch('/api/v1/chat/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
      const data = await response.json()
      setMessages((current) => [...current, { role: 'assistant', text: data.text }])
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
        <button className="nav-item">✓ <span>Tarefas</span></button>
        <button className="nav-item">◷ <span>Agenda</span></button>
        <button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>⚙ <span>Configuração</span></button>
      </nav>
      <div className="status"><span className="dot" /> Sistema online<br /><small>Modo de desenvolvimento</small></div>
    </aside>
    <section className="content">
      {view === 'settings' ? <Settings config={config} /> : <>
        <header className="topbar"><div><p className="eyebrow">CENTRAL DE COMANDO</p><h1>Bom dia, Eduardo</h1></div><div className="avatar">E</div></header>
        <div className="conversation">
          <div className="welcome"><div className="orb">✦</div><h2>Em que posso ajudar?</h2><p>Peça para organizar suas tarefas, notas e compromissos.</p><div className="suggestions"><button onClick={() => setInput('O que tenho para fazer hoje?')}>O que tenho para fazer hoje?</button><button onClick={() => setInput('Crie uma tarefa no ClickUp')}>Criar tarefa no ClickUp</button><button onClick={() => setInput('Salve uma nota no Notion')}>Salvar nota no Notion</button></div></div>
          <div className="messages">{messages.map((message, index) => <div key={index} className={`message ${message.role}`}><span>{message.transcription && <small className="transcription">Transcrição: {message.transcription}</small>}{message.text}</span></div>)}</div>
        </div>
        <form className="composer" onSubmit={sendMessage}><label className="audio-button" title="Enviar áudio">🎙 Áudio<input type="file" accept="audio/*,.mp3,.wav,.m4a,.ogg,.webm" hidden onChange={(e) => { const file = e.target.files?.[0]; if (file) sendAudio(file); e.currentTarget.value = '' }} /></label><input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Fale com a Sofia..." aria-label="Mensagem"/><button disabled={sending || !input.trim()}>{sending ? '…' : 'Enviar'} <span>↗</span></button></form>
        <p className="hint">Você também pode clicar em <strong>🎙 Áudio</strong> para enviar uma gravação.</p>
      </>}
    </section>
  </main>
}

function Settings({ config }: { config: Config | null }) {
  return <div className="settings-page"><p className="eyebrow">CONFIGURAÇÃO</p><h1>Inteligência da Sofia</h1><p className="settings-lead">Informações técnicas disponíveis apenas nesta área de administração.</p><div className="settings-card"><div className="setting-row"><span>Provedor principal</span><strong>{config?.ai_provider || 'Carregando…'}</strong></div><div className="setting-row"><span>Groq</span><strong className={config?.groq_configured ? 'ok' : 'muted'}>{config?.groq_configured ? 'Configurado' : 'Não configurado'}</strong></div><div className="setting-row"><span>OpenRouter</span><strong className={config?.openrouter_configured ? 'ok' : 'muted'}>{config?.openrouter_configured ? 'Configurado' : 'Não configurado'}</strong></div><div className="setting-row"><span>Modelo de conversa Groq</span><strong>{config?.groq_model || 'llama-3.3-70b-versatile'}</strong></div><div className="setting-row"><span>Modelo de transcrição</span><strong>{config?.groq_transcription_model || 'whisper-large-v3-turbo'}</strong></div><div className="setting-row"><span>Ambiente</span><strong>{config?.environment || 'development'}</strong></div></div><p className="settings-note">As chaves permanecem somente no backend e nunca são exibidas.</p></div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
