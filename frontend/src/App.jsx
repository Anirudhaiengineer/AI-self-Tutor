import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const API_BASE_URL = 'http://127.0.0.1:8000'

const initialFormState = {
  name: '',
  email: '',
  password: '',
}

const emptyPlan = { goal: '', accepted: false, slots: [], calendar: [], schedule_type: 'short' }

function App() {
  const [mode, setMode] = useState('login')
  const [page, setPage] = useState('auth')
  const [scheduleType, setScheduleType] = useState('short')
  const [formData, setFormData] = useState(initialFormState)
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')
  const [authSuccess, setAuthSuccess] = useState('')
  const [authData, setAuthData] = useState(null)
  const [goalInput, setGoalInput] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [planLoading, setPlanLoading] = useState(false)
  const [planError, setPlanError] = useState('')
  const [learningPlan, setLearningPlan] = useState(emptyPlan)
  const [serviceStatus, setServiceStatus] = useState(null)
  const [serviceError, setServiceError] = useState('')
  const [serviceLoading, setServiceLoading] = useState(false)
  const [transcripts, setTranscripts] = useState([])
  const [summaryData, setSummaryData] = useState({ summary: '', highlights: [], keywords: [] })
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatMessages, setChatMessages] = useState([
    {
      role: 'assistant',
      content: 'Ask about the transcript or ask a general concept question. I will use transcript context when it helps and general knowledge when it does not.',
    },
  ])
  const [schedulePrompt, setSchedulePrompt] = useState(null)
  const notifiedSlotsRef = useRef(new Set())

  const transcriptText = useMemo(() => {
    if (transcripts.length === 0) {
      return 'Transcribed text will appear here while the recorder is running.'
    }

    return transcripts
      .map((item) => `[${new Date(item.created_at).toLocaleTimeString()}] ${item.text}`)
      .join('\n')
  }, [transcripts])

  const activeSlot = useMemo(() => {
    const now = new Date()
    return (learningPlan.slots || []).find((slot) => {
      const start = new Date(slot.start_at)
      const end = new Date(slot.end_at)
      return slot.status !== 'completed' && slot.status !== 'postponed' && now >= start && now < end
    }) || null
  }, [learningPlan])

  useEffect(() => {
    if (page !== 'dashboard' || !authData) {
      return undefined
    }

    let pollingId

    async function loadDashboardData() {
      try {
        const [statusResponse, transcriptResponse, summaryResponse, planResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/services/status`),
          fetch(`${API_BASE_URL}/services/transcripts`),
          fetch(`${API_BASE_URL}/services/summary`),
          fetch(`${API_BASE_URL}/learning/plan/${encodeURIComponent(authData.user.email)}`),
        ])

        const statusData = await statusResponse.json()
        const transcriptData = await transcriptResponse.json()
        const summary = await summaryResponse.json()
        const plan = await planResponse.json()

        if (!statusResponse.ok || !transcriptResponse.ok || !summaryResponse.ok || !planResponse.ok) {
          throw new Error('Unable to load dashboard data')
        }

        setServiceStatus(statusData)
        setTranscripts(transcriptData.items || [])
        setSummaryData(summary)
        setLearningPlan(plan)
        setServiceError('')
      } catch (error) {
        setServiceError(error.message || 'Unable to connect to backend services')
      }
    }

    loadDashboardData()
    pollingId = window.setInterval(loadDashboardData, 15000)

    return () => window.clearInterval(pollingId)
  }, [page, authData])

  useEffect(() => {
    if (page !== 'dashboard') {
      return undefined
    }

    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }

    const timer = window.setInterval(() => {
      const now = new Date()
      const endedSlot = (learningPlan.slots || []).find((slot) => {
        const end = new Date(slot.end_at)
        return slot.status !== 'completed' && slot.status !== 'postponed' && now >= end
      })

      if (!endedSlot) {
        return
      }

      if (notifiedSlotsRef.current.has(endedSlot.slot_id)) {
        return
      }

      notifiedSlotsRef.current.add(endedSlot.slot_id)
      setSchedulePrompt(endedSlot)

      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Study slot ended', {
          body: `Did you complete ${endedSlot.topic}?`,
        })
      }
    }, 10000)

    return () => window.clearInterval(timer)
  }, [page, learningPlan])

  function handleChange(event) {
    const { name, value } = event.target
    setFormData((current) => ({ ...current, [name]: value }))
  }

  function switchMode(nextMode) {
    setMode(nextMode)
    setAuthError('')
    setAuthSuccess('')
    setFormData(initialFormState)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setAuthLoading(true)
    setAuthError('')
    setAuthSuccess('')

    const endpoint = mode === 'register' ? '/auth/register' : '/auth/login'
    const payload = mode === 'register'
      ? formData
      : { email: formData.email, password: formData.password }

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Request failed')
      }

      setAuthSuccess(data.message)
      setAuthData(data)
      setFormData(initialFormState)
      setPage('schedule-type')
    } catch (requestError) {
      setAuthError(requestError.message || 'Unable to connect to the server')
    } finally {
      setAuthLoading(false)
    }
  }

  function chooseScheduleType(type) {
    setScheduleType(type)
    setPlanError('')
    setGoalInput('')
    setStartDate('')
    setEndDate('')
    setLearningPlan(emptyPlan)
    setPage(type === 'short' ? 'goal-short' : 'goal-long')
  }

  async function generatePlan(event) {
    event.preventDefault()
    if (!goalInput.trim() || !authData) {
      return
    }

    if (scheduleType === 'long' && (!startDate || !endDate)) {
      setPlanError('Please choose both a start date and an end date.')
      return
    }

    setPlanLoading(true)
    setPlanError('')
    try {
      const response = await fetch(`${API_BASE_URL}/learning/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: authData.user.email,
          goal: goalInput.trim(),
          schedule_type: scheduleType,
          start_date: scheduleType === 'long' ? startDate : null,
          end_date: scheduleType === 'long' ? endDate : null,
        }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to create learning plan')
      }
      setLearningPlan(data)
    } catch (error) {
      setPlanError(error.message || 'Unable to create learning plan')
    } finally {
      setPlanLoading(false)
    }
  }

  async function acceptPlan() {
    if (!authData) {
      return
    }

    setPlanLoading(true)
    setPlanError('')
    try {
      const response = await fetch(`${API_BASE_URL}/learning/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: authData.user.email }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to accept learning plan')
      }
      setLearningPlan(data)
      setPage('dashboard')
      await updateRecording('start', true)
    } catch (error) {
      setPlanError(error.message || 'Unable to accept learning plan')
    } finally {
      setPlanLoading(false)
    }
  }

  async function updateRecording(action, silent = false) {
    setServiceLoading(true)
    if (!silent) {
      setServiceError('')
    }

    try {
      const response = await fetch(`${API_BASE_URL}/services/${action}`, { method: 'POST' })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || `Unable to ${action} recording`)
      }
      setServiceStatus(data.services)
    } catch (error) {
      setServiceError(error.message || 'Unable to update recorder state')
    } finally {
      setServiceLoading(false)
    }
  }

  async function handleSlotAction(action) {
    if (!schedulePrompt || !authData) {
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/learning/slot-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: authData.user.email, slot_id: schedulePrompt.slot_id, action }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to update study slot')
      }
      if (action === 'continue') {
        notifiedSlotsRef.current.delete(schedulePrompt.slot_id)
      }
      setLearningPlan(data)
      setSchedulePrompt(null)
    } catch (error) {
      setServiceError(error.message || 'Unable to update study slot')
    }
  }

  async function sendChat(event) {
    event.preventDefault()
    const message = chatInput.trim()
    if (!message) {
      return
    }

    setChatLoading(true)
    setChatMessages((current) => [...current, { role: 'user', content: message }])
    setChatInput('')

    try {
      const response = await fetch(`${API_BASE_URL}/services/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to get chatbot response')
      }
      setChatMessages((current) => [...current, { role: 'assistant', content: data.answer }])
    } catch (error) {
      setChatMessages((current) => [...current, { role: 'assistant', content: error.message || 'Unable to answer right now.' }])
    } finally {
      setChatLoading(false)
    }
  }

  function logout() {
    setPage('auth')
    setScheduleType('short')
    setAuthData(null)
    setAuthSuccess('')
    setAuthError('')
    setGoalInput('')
    setStartDate('')
    setEndDate('')
    setLearningPlan(emptyPlan)
    setPlanError('')
    setServiceError('')
    setServiceStatus(null)
    setTranscripts([])
    setSummaryData({ summary: '', highlights: [], keywords: [] })
    setChatMessages([{ role: 'assistant', content: 'Ask about the transcript or ask a general concept question. I will use transcript context when it helps and general knowledge when it does not.' }])
    setChatInput('')
    setSchedulePrompt(null)
    notifiedSlotsRef.current = new Set()
    setFormData(initialFormState)
  }

  function formatTime(dateString) {
    return new Date(dateString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const isRecording = Boolean(serviceStatus?.audio_listener?.capture_enabled)

  if (page === 'schedule-type' && authData) {
    return (
      <main className="auth-shell solo-auth">
        <section className="auth-page planner-page schedule-choice-page">
          <p className="eyebrow">Schedule Mode</p>
          <h1>Short-term or long-term schedule?</h1>
          <p className="hero-copy">Choose how you want to study today. Short-term keeps the current same-day flow. Long-term asks for dates and builds a calendar-style plan.</p>
          <div className="choice-grid">
            <button type="button" className="choice-card" onClick={() => chooseScheduleType('short')}>
              <span className="choice-label">Short Term</span>
              <strong>Plan for today</strong>
              <p>Continue with the present workflow and build a schedule for the current session.</p>
            </button>
            <button type="button" className="choice-card" onClick={() => chooseScheduleType('long')}>
              <span className="choice-label">Long Term</span>
              <strong>Plan with dates</strong>
              <p>Pick a start and end date and get a calendar that labels each day with the work.</p>
            </button>
          </div>
        </section>
      </main>
    )
  }

  if ((page === 'goal-short' || page === 'goal-long') && authData) {
    const isLong = scheduleType === 'long'
    return (
      <main className="auth-shell solo-auth">
        <section className="auth-page planner-page">
          <p className="eyebrow">Today&apos;s Goal</p>
          <h1>{isLong ? 'Create a long-term learning calendar' : 'Create a study schedule for today'}</h1>
          <p className="hero-copy">{isLong ? 'Describe the goal, choose your dates, and we will build a labeled calendar of work for each day.' : 'Tell the system what you want to learn today. It will identify the main topics, subtopics, and a realistic order for learning before asking you to accept the schedule.'}</p>

          <form className="auth-form" onSubmit={generatePlan}>
            <label>
              <span>What do you want to learn?</span>
              <textarea
                className="goal-input"
                value={goalInput}
                onChange={(event) => setGoalInput(event.target.value)}
                placeholder="Example: stacks and queues, binary trees, dynamic programming"
                rows={4}
                required
              />
            </label>

            {isLong && (
              <div className="date-row">
                <label>
                  <span>Start date</span>
                  <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required />
                </label>
                <label>
                  <span>End date</span>
                  <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} required />
                </label>
              </div>
            )}

            <button className="submit-button" type="submit" disabled={planLoading}>
              {planLoading ? 'Generating...' : 'Generate schedule'}
            </button>
          </form>

          {learningPlan.slots?.length > 0 && (
            <div className="plan-preview">
              <div className="card-header">
                <div>
                  <p className="eyebrow">{isLong ? 'Calendar Preview' : 'Schedule Preview'}</p>
                  <h2>{learningPlan.goal}</h2>
                </div>
              </div>
              {learningPlan.summary && <p className="summary-copy">{learningPlan.summary}</p>}
              <div className="slot-list light-surface">
                {learningPlan.slots.map((slot) => (
                  <div key={slot.slot_id} className="slot-item light-slot">
                    <strong>{isLong ? `${slot.date} - ${slot.topic}` : slot.topic}</strong>
                    {slot.description && <span>{slot.description}</span>}
                    <span>{isLong ? `Work for ${slot.date}` : `${formatTime(slot.start_at)} - ${formatTime(slot.end_at)} ${slot.estimated_minutes ? `(${slot.estimated_minutes} min)` : ''}`}</span>
                    {Array.isArray(slot.subtopics) && slot.subtopics.length > 0 && (
                      <div className="keyword-row">
                        {slot.subtopics.map((subtopic) => (
                          <span key={`${slot.slot_id}-${subtopic}`} className="keyword-chip">{subtopic}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <button className="submit-button" type="button" onClick={acceptPlan} disabled={planLoading}>
                {planLoading ? 'Please wait...' : 'Accept schedule and start'}
              </button>
            </div>
          )}

          {planError && <p className="message error">{planError}</p>}
        </section>
      </main>
    )
  }

  if (page === 'dashboard' && authData) {
    const isLong = learningPlan.schedule_type === 'long'
    return (
      <main className="dashboard-shell workspace-layout">
        <section className="dashboard-topbar">
          <div>
            <p className="eyebrow">Recorder workspace</p>
            <h1 className="dashboard-title">Welcome, {authData.user.name}</h1>
            {activeSlot && <p className="hero-copy">Current slot: {activeSlot.topic} until {formatTime(activeSlot.end_at)}</p>}
          </div>
          <button type="button" className="ghost-button" onClick={logout}>Logout</button>
        </section>

        <section className="schedule-card summary-card">
          <div className="card-header">
            <div>
              <p className="eyebrow">{isLong ? 'Calendar' : 'Today&apos;s Schedule'}</p>
              <h2>{learningPlan.goal || 'No goal loaded'}</h2>
            </div>
          </div>
          {learningPlan.summary && <p className="summary-copy">{learningPlan.summary}</p>}
          <div className="slot-list">
            {(learningPlan.slots || []).map((slot) => (
              <div key={slot.slot_id} className={`slot-item ${activeSlot?.slot_id === slot.slot_id ? 'active-slot' : ''}`}>
                <strong>{isLong ? `${slot.date} - ${slot.topic}` : slot.topic}</strong>
                {slot.description && <span>{slot.description}</span>}
                <span>{isLong ? `Work for ${slot.date}` : `${formatTime(slot.start_at)} - ${formatTime(slot.end_at)} ${slot.estimated_minutes ? `(${slot.estimated_minutes} min)` : ''}`}</span>
                {Array.isArray(slot.subtopics) && slot.subtopics.length > 0 && (
                  <div className="keyword-row">
                    {slot.subtopics.map((subtopic) => (
                      <span key={`${slot.slot_id}-${subtopic}`} className="keyword-chip">{subtopic}</span>
                    ))}
                  </div>
                )}
                <small>Status: {slot.status}</small>
              </div>
            ))}
          </div>
        </section>

        <section className="transcript-panel recorder-card">
          <div className="recorder-header">
            <div>
              <p className="eyebrow">System Audio</p>
              <h2>Live transcription console</h2>
            </div>
            <div className={`recording-pill ${isRecording ? 'live' : ''}`}>{isRecording ? 'Recording' : 'Stopped'}</div>
          </div>

          <p className="panel-copy light-copy">The recorder starts after you accept the schedule. When a slot ends, you&apos;ll be asked whether the topic is completed, should continue, or should be postponed.</p>

          <div className="recorder-actions">
            <button type="button" className="record-button start" onClick={() => updateRecording('start')} disabled={serviceLoading || isRecording}>Start Recording</button>
            <button type="button" className="record-button stop" onClick={() => updateRecording('stop')} disabled={serviceLoading || !isRecording}>Stop Recording</button>
          </div>

          <div className="service-meta">
            <span>Audio: {serviceStatus?.audio_listener?.status || 'unknown'}</span>
            <span>STT: {serviceStatus?.speech_to_text?.status || 'unknown'}</span>
            <span>Mode: {serviceStatus?.speech_to_text?.mode || 'unknown'}</span>
          </div>

          {serviceStatus?.audio_listener?.last_error && <p className="message warning">{serviceStatus.audio_listener.last_error}</p>}

          <label className="transcript-box">
            <span>Live transcript</span>
            <textarea value={transcriptText} readOnly rows={12} />
          </label>

          {serviceError && <p className="message error">{serviceError}</p>}
        </section>

        <section className="summary-card">
          <div className="card-header">
            <div>
              <p className="eyebrow">RAG Summary</p>
              <h2>Transcript snapshot</h2>
            </div>
          </div>
          <p className="summary-copy">{summaryData.summary || 'A summary will appear after transcript content is available.'}</p>
          <div className="keyword-row">
            {(summaryData.keywords || []).map((keyword) => <span key={keyword} className="keyword-chip">{keyword}</span>)}
          </div>
          <div className="highlight-list">
            {(summaryData.highlights || []).map((item, index) => <div key={`${item}-${index}`} className="highlight-item">{item}</div>)}
          </div>
        </section>

        <section className="chat-card">
          <div className="card-header">
            <div>
              <p className="eyebrow">Chatbot</p>
              <h2>Ask about the transcript or any concept</h2>
            </div>
          </div>
          <div className="chat-log">
            {chatMessages.map((message, index) => <div key={`${message.role}-${index}`} className={`chat-bubble ${message.role}`}>{message.content}</div>)}
          </div>
          <form className="chat-form" onSubmit={sendChat}>
            <textarea value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask about the transcript, or ask a general doubt like 'what is a dynamic language?'" rows={3} />
            <button type="submit" className="submit-button" disabled={chatLoading}>{chatLoading ? 'Thinking...' : 'Send'}</button>
          </form>
        </section>

        {schedulePrompt && (
          <div className="modal-backdrop">
            <div className="modal-card">
              <p className="eyebrow">Slot Check-in</p>
              <h2>{schedulePrompt.topic}</h2>
              <p className="hero-copy">This study slot has ended. Was the topic completed, should it continue for 30 more minutes, or should it be postponed to later today?</p>
              <div className="modal-actions">
                <button type="button" className="submit-button" onClick={() => handleSlotAction('complete')}>Completed</button>
                <button type="button" className="record-button start" onClick={() => handleSlotAction('continue')}>Continue</button>
                <button type="button" className="record-button stop" onClick={() => handleSlotAction('postpone')}>Postpone</button>
              </div>
            </div>
          </div>
        )}
      </main>
    )
  }

  return (
    <main className="auth-shell solo-auth">
      <section className="auth-panel auth-page">
        <p className="eyebrow">Project 1</p>
        <h1>Login or register to open the recorder</h1>
        <p className="hero-copy">Authentication now lives on its own page. After login, you will choose a schedule type before the planner and then the transcription dashboard.</p>
        <div className="mode-switch" role="tablist" aria-label="Authentication mode">
          <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => switchMode('login')}>Login</button>
          <button type="button" className={mode === 'register' ? 'active' : ''} onClick={() => switchMode('register')}>Register</button>
        </div>
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === 'register' && (
            <label>
              <span>Name</span>
              <input name="name" type="text" placeholder="Enter your name" value={formData.name} onChange={handleChange} required />
            </label>
          )}
          <label>
            <span>Email</span>
            <input name="email" type="email" placeholder="Enter your email" value={formData.email} onChange={handleChange} required />
          </label>
          <label>
            <span>Password</span>
            <input name="password" type="password" placeholder="Enter your password" value={formData.password} onChange={handleChange} required />
          </label>
          <button className="submit-button" type="submit" disabled={authLoading}>{authLoading ? 'Please wait...' : mode === 'register' ? 'Create account' : 'Login'}</button>
        </form>
        {authError && <p className="message error">{authError}</p>}
        {authSuccess && <p className="message success">{authSuccess}</p>}
      </section>
    </main>
  )
}

export default App
