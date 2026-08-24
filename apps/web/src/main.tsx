import React, { FormEvent, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Message = { role: 'assistant' | 'user'; text: string }

function App() {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', text: 'Olá! Eu sou a Sofia. Como posso ajudar você hoje?' },
  ])

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages((current) => [...current, { role: 'user', text }])
    setSending(true)
    try {
      const response = await fetch('/api/v1/chat/messages', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
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
      <nav><button className="nav-item active">◌ <span>Conversa</span></button><button className="nav-item">✓ <span>Tarefas</span></button><button className="nav-item">◷ <span>Agenda</span></button></nav>
      <div className="status"><span className="dot" /> Sistema online<br /><small>Modo de desenvolvimento</small></div>
    </aside>
    <section className="content">
      <header className="topbar"><div><p className="eyebrow">CENTRAL DE COMANDO</p><h1>Bom dia, Eduardo</h1></div><div className="avatar">E</div></header>
      <div className="conversation">
        <div className="welcome"><div className="orb">✦</div><h2>Em que posso ajudar?</h2><p>Peça para organizar suas tarefas, notas e compromissos.</p><div className="suggestions"><button onClick={() => setInput('O que tenho para fazer hoje?')}>O que tenho para fazer hoje?</button><button onClick={() => setInput('Crie uma tarefa no ClickUp')}>Criar tarefa no ClickUp</button><button onClick={() => setInput('Salve uma nota no Notion')}>Salvar nota no Notion</button></div></div>
        <div className="messages">{messages.map((message, index) => <div key={index} className={`message ${message.role}`}><span>{message.text}</span></div>)}</div>
      </div>
      <form className="composer" onSubmit={sendMessage}><input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Fale com a Sofia..." aria-label="Mensagem"/><button disabled={sending || !input.trim()}>{sending ? '…' : 'Enviar'} <span>↗</span></button></form>
      <p className="hint">A Sofia pedirá sua confirmação antes de realizar ações importantes.</p>
    </section>
  </main>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
