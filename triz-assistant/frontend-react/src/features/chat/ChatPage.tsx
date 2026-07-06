import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useNavigate } from 'react-router-dom'

import AnalyticsIcon from '@mui/icons-material/Analytics'
import FastForwardIcon from '@mui/icons-material/FastForward'

import Alert from '@mui/material/Alert'

import Box from '@mui/material/Box'

import Button from '@mui/material/Button'

import CircularProgress from '@mui/material/CircularProgress'

import Divider from '@mui/material/Divider'

import useMediaQuery from '@mui/material/useMediaQuery'

import { useTheme } from '@mui/material/styles'

import {

  filterVisibleMessages,
  isAbortError,
  isSessionNotFoundError,
  trizApi,

  useCreateChatSessionMutation,

  useCreateSolveJobMutation,

  useDeleteChatSessionMutation,

  useGetActiveChatQuery,

  useGetChatSessionQuery,

  useListChatSessionsQuery,

  useSendChatMessageMutation,

  useLazyGetSolveJobStatusQuery,

  useSetActiveChatMutation,

} from '../../app/api'

import type { AnalysisProfile } from '../../types/triz'

import { AnalysisProgressOverlay } from '../../components/AnalysisProgressOverlay'
import { Layout } from '../../components/Layout'

import { ProgressStepper } from '../../components/ProgressStepper'

import { AnalysisProfilePanel } from './AnalysisProfilePanel'
import { ChatInput } from './ChatInput'

import { ChatMessageList } from './ChatMessageList'

import { getInterviewBlockStatus } from './interviewProgress'

import { SessionsDrawer } from './SessionsDrawer'


const SOLVE_JOB_KEY_PREFIX = 'triz-solve-job:'
const SOLVE_JOB_POLL_MS = 2000

function storedSolveJobId(sessionId: string): string | null {
  return sessionStorage.getItem(`${SOLVE_JOB_KEY_PREFIX}${sessionId}`)
}

function storeSolveJobId(sessionId: string, jobId: string): void {
  sessionStorage.setItem(`${SOLVE_JOB_KEY_PREFIX}${sessionId}`, jobId)
}

function clearStoredSolveJobId(sessionId: string): void {
  sessionStorage.removeItem(`${SOLVE_JOB_KEY_PREFIX}${sessionId}`)
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}


export function ChatPage() {

  const theme = useTheme()

  const isDesktop = useMediaQuery(theme.breakpoints.up('md'))

  const navigate = useNavigate()

  const dispatch = useAppDispatch()



  const [sessionId, setSessionId] = useState<string | null>(null)

  const [drawerOpen, setDrawerOpen] = useState(false)

  const [initDone, setInitDone] = useState(false)

  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const recoveringSessionRef = useRef(false)



  const { data: sessionsData, isLoading: sessionsLoading } = useListChatSessionsQuery(50)

  const { data: activeChat } = useGetActiveChatQuery()

  const {
    data: sessionData,
    isLoading: sessionLoading,
    isError: sessionError,
    error: sessionQueryError,
  } = useGetChatSessionQuery(sessionId!, {

    skip: !sessionId,

    refetchOnMountOrArgChange: true,

  })



  const session = sessionData?.id === sessionId ? sessionData : undefined
  const isSessionLoading = Boolean(sessionId) && !isCreatingSession && sessionLoading && !session



  const [createSession] = useCreateChatSessionMutation()

  const [sendMessage, { isLoading: sending }] = useSendChatMessageMutation()

  const [createSolveJob] = useCreateSolveJobMutation()
  const [fetchSolveJobStatus] = useLazyGetSolveJobStatusQuery()

  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeProgress, setAnalyzeProgress] = useState(0)
  const [analyzeStage, setAnalyzeStage] = useState('')
  const [analysisProfile, setAnalysisProfile] = useState<AnalysisProfile | undefined>(undefined)
  const resumeJobRef = useRef<string | null>(null)
  const pollAbortControllerRef = useRef<AbortController | null>(null)

  const beginPolling = useCallback(() => {
    pollAbortControllerRef.current?.abort()
    const controller = new AbortController()
    pollAbortControllerRef.current = controller
    return controller.signal
  }, [])

  useEffect(() => {
    return () => {
      pollAbortControllerRef.current?.abort()
    }
  }, [])

  const [deleteSession] = useDeleteChatSessionMutation()

  const [setActiveChat] = useSetActiveChatMutation()

  const ensureFreshSession = useCallback(async () => {
    const created = await createSession().unwrap()
    setSessionId(created.id)
    await setActiveChat(created.id).unwrap()
    return created.id
  }, [createSession, setActiveChat])

  useEffect(() => {
    if (initDone) return

    const init = async () => {
      const restoredId = activeChat?.session_id
      if (restoredId) {
        try {
          await dispatch(
            trizApi.endpoints.getChatSession.initiate(restoredId, { forceRefetch: true }),
          ).unwrap()
          setSessionId(restoredId)
          setInitDone(true)
          return
        } catch {
          /* restored session missing on server — create below */
        }
      }

      try {
        await ensureFreshSession()
      } catch {
        /* handled by UI */
      }
      setInitDone(true)
    }

    if (activeChat !== undefined) {
      void init()
    }
  }, [activeChat, dispatch, ensureFreshSession, initDone])

  useEffect(() => {
    if (!initDone || !sessionId || isCreatingSession || !sessionError) return
    if (!isSessionNotFoundError(sessionQueryError)) return
    if (recoveringSessionRef.current) return

    recoveringSessionRef.current = true
    const recover = async () => {
      try {
        await ensureFreshSession()
        setSendError('Предыдущий диалог недоступен — создан новый.')
      } catch {
        setSendError('Не удалось восстановить диалог. Обновите страницу.')
      } finally {
        recoveringSessionRef.current = false
      }
    }
    void recover()
  }, [initDone, sessionId, isCreatingSession, sessionError, sessionQueryError, ensureFreshSession])



  const visibleMessages = useMemo(

    () => filterVisibleMessages(session?.messages ?? []),

    [session?.messages],

  )



  const blockStatus = useMemo(

    () => getInterviewBlockStatus(session?.messages ?? []),

    [session?.messages],

  )



  const status = session?.status ?? 'interview'

  const hasUserReply = useMemo(
    () => visibleMessages.some((m) => m.role === 'user'),
    [visibleMessages],
  )

  const canSend = status === 'interview' && !sending

  const canAnalyze = status === 'ready' && !analyzing

  const canForceAnalyze = status === 'interview' && hasUserReply && !analyzing && !sending

  const isAnalyzed = status === 'analyzed'



  const handleSend = useCallback(
    async (content: string) => {
      if (!sessionId) return
      setSendError(null)
      try {
        await sendMessage({ sessionId, content }).unwrap()
      } catch (err) {
        if (isSessionNotFoundError(err)) {
          try {
            const newId = await ensureFreshSession()
            setSendError('Диалог пересоздан — отправьте сообщение ещё раз.')
            await sendMessage({ sessionId: newId, content }).unwrap()
            setSendError(null)
            return
          } catch (retryErr) {
            const message =
              retryErr && typeof retryErr === 'object' && 'data' in retryErr
                ? String((retryErr as { data?: { detail?: string } }).data?.detail ?? 'Не удалось отправить сообщение')
                : 'Не удалось отправить сообщение'
            setSendError(message)
            return
          }
        }
        const message =
          err && typeof err === 'object' && 'data' in err
            ? String((err as { data?: { detail?: string } }).data?.detail ?? 'Не удалось отправить сообщение')
            : 'Не удалось отправить сообщение'
        setSendError(message)
      }
    },
    [sessionId, sendMessage, ensureFreshSession],
  )



  const handleNewSession = useCallback(async () => {

    setIsCreatingSession(true)

    try {

      const created = await createSession().unwrap()
      setSessionId(created.id)
      await setActiveChat(created.id).unwrap()

      if (!isDesktop) setDrawerOpen(false)

    } catch (err) {

      console.error('Не удалось создать диалог:', err)

    } finally {

      setIsCreatingSession(false)

    }

  }, [createSession, setActiveChat, isDesktop])



  const handleSelectSession = useCallback(

    async (id: string) => {

      setSessionId(id)

      dispatch(trizApi.endpoints.getChatSession.initiate(id, { forceRefetch: true }))

      await setActiveChat(id).unwrap()

      if (!isDesktop) setDrawerOpen(false)

    },

    [setActiveChat, dispatch, isDesktop],

  )



  const handleDeleteSession = useCallback(

    async (id: string) => {

      await deleteSession(id).unwrap()

      if (sessionId === id) {

        const created = await createSession().unwrap()

        setSessionId(created.id)

        await setActiveChat(created.id).unwrap()

      }

    },

    [deleteSession, sessionId, createSession, setActiveChat],

  )



  const finishSuccessfulJob = useCallback(
    (sid: string, brief: string, result: import('../../types/triz').SolveResponse) => {
      clearStoredSolveJobId(sid)
      dispatch(
        trizApi.util.invalidateTags([
          { type: 'ChatSession', id: sid },
          { type: 'ChatSessionList', id: 'LIST' },
          { type: 'Report', id: sid },
          { type: 'History', id: 'LIST' },
        ]),
      )
      navigate(`/report/${sid}`, { state: { brief, result } })
    },
    [dispatch, navigate],
  )

  const pollSolveJob = useCallback(
    async (jobId: string, sid: string, brief: string, signal: AbortSignal) => {
      while (true) {
        if (signal.aborted) return
        await sleep(SOLVE_JOB_POLL_MS)
        if (signal.aborted) return
        try {
          const status = await fetchSolveJobStatus({ jobId, signal }).unwrap()
          if (signal.aborted) return
          setAnalyzeProgress(status.progress.pct)
          setAnalyzeStage(status.progress.stage)
          if (status.status === 'done' && status.result) {
            finishSuccessfulJob(sid, brief, status.result)
            return
          }
          if (status.status === 'error') {
            clearStoredSolveJobId(sid)
            setSendError(status.error ?? 'Не удалось выполнить анализ')
            return
          }
        } catch (err) {
          if (isAbortError(err)) return
          /* polling errors are non-fatal */
        }
      }
    },
    [fetchSolveJobStatus, finishSuccessfulJob],
  )

  const runAnalysis = useCallback(
    async (options?: { force?: boolean }) => {
      if (!sessionId) return

      const signal = beginPolling()

      setAnalyzing(true)
      setAnalyzeProgress(0)
      setAnalyzeStage(options?.force ? 'Принудительное завершение анкеты…' : 'Запуск анализа…')
      setSendError(null)

      try {
        const created = await createSolveJob({
          problem: session?.brief ?? 'chat',
          chat_session_id: sessionId,
          force: options?.force ?? false,
          ...(analysisProfile ? { profile: analysisProfile } : {}),
        }).unwrap()
        if (signal.aborted) return
        storeSolveJobId(sessionId, created.job_id)

        const brief = session?.brief ?? ''
        const status = await fetchSolveJobStatus({ jobId: created.job_id, signal }).unwrap()
        if (signal.aborted) return
        setAnalyzeProgress(status.progress.pct)
        setAnalyzeStage(status.progress.stage)

        if (status.status === 'done' && status.result) {
          finishSuccessfulJob(sessionId, brief, status.result)
          return
        }
        if (status.status === 'error') {
          clearStoredSolveJobId(sessionId)
          setSendError(status.error ?? 'Не удалось выполнить анализ')
          return
        }

        await pollSolveJob(created.job_id, sessionId, brief, signal)
      } catch (err) {
        if (isAbortError(err)) return
        const message =
          err && typeof err === 'object' && 'data' in err
            ? String((err as { data?: { detail?: string } }).data?.detail ?? 'Не удалось выполнить анализ')
            : 'Не удалось выполнить анализ'
        setSendError(message)
      } finally {
        if (!signal.aborted) {
          setAnalyzing(false)
        }
      }
    },
    [sessionId, session?.brief, analysisProfile, beginPolling, createSolveJob, fetchSolveJobStatus, pollSolveJob, finishSuccessfulJob],
  )

  useEffect(() => {
    if (!initDone || !sessionId || analyzing) return
    const storedJobId = storedSolveJobId(sessionId)
    if (!storedJobId) return
    if (resumeJobRef.current === `${sessionId}:${storedJobId}`) return
    resumeJobRef.current = `${sessionId}:${storedJobId}`

    const resume = async () => {
      const signal = beginPolling()
      setAnalyzing(true)
      const brief = session?.brief ?? ''
      try {
        const status = await fetchSolveJobStatus({ jobId: storedJobId, signal }).unwrap()
        if (signal.aborted) return
        setAnalyzeProgress(status.progress.pct)
        setAnalyzeStage(status.progress.stage)
        if (status.status === 'done' && status.result) {
          finishSuccessfulJob(sessionId, brief, status.result)
          return
        }
        if (status.status === 'error') {
          clearStoredSolveJobId(sessionId)
          setSendError(status.error ?? 'Не удалось выполнить анализ')
          return
        }
        await pollSolveJob(storedJobId, sessionId, brief, signal)
      } catch (err) {
        if (isAbortError(err)) return
        clearStoredSolveJobId(sessionId)
      } finally {
        if (!signal.aborted) {
          setAnalyzing(false)
        }
      }
    }

    void resume()
  }, [
    initDone,
    sessionId,
    analyzing,
    session?.brief,
    beginPolling,
    fetchSolveJobStatus,
    pollSolveJob,
    finishSuccessfulJob,
  ])

  const handleAnalyze = useCallback(() => {
    void runAnalysis()
  }, [runAnalysis])

  const handleForceCompleteAndAnalyze = useCallback(() => {
    void runAnalysis({ force: true })
  }, [runAnalysis])



  const handleOpenReport = useCallback(() => {

    if (sessionId) navigate(`/report/${sessionId}`)

  }, [sessionId, navigate])



  return (

    <Box

      sx={{

        height: '100dvh',

        overflow: 'hidden',

        display: 'flex',

        flexDirection: 'row',

      }}

    >

      {isDesktop ? (

        <SessionsDrawer

          open

          variant="permanent"

          onClose={() => setDrawerOpen(false)}

          sessions={sessionsData?.items ?? []}

          activeSessionId={sessionId}

          onSelect={handleSelectSession}

          onNew={handleNewSession}

          onDelete={handleDeleteSession}

          isLoading={sessionsLoading}

          isCreating={isCreatingSession}

        />

      ) : (

        <SessionsDrawer

          open={drawerOpen}

          variant="temporary"

          onClose={() => setDrawerOpen(false)}

          sessions={sessionsData?.items ?? []}

          activeSessionId={sessionId}

          onSelect={handleSelectSession}

          onNew={handleNewSession}

          onDelete={handleDeleteSession}

          isLoading={sessionsLoading}

          isCreating={isCreatingSession}

        />

      )}

      {analyzing && (
        <AnalysisProgressOverlay progress={analyzeProgress} stage={analyzeStage} />
      )}

      <Layout

        sessionTitle={session?.title}

        sessionStatus={status}

        onMenuClick={isDesktop ? undefined : () => setDrawerOpen(true)}

        actions={

          isAnalyzed ? (

            <Button size="small" onClick={handleOpenReport} sx={{ minHeight: 44 }}>

              Отчёт

            </Button>

          ) : undefined

        }

        headerExtra={

          <>

            <Divider />

            <ProgressStepper

              blocks={blockStatus}

              sessionStatus={status}

              hasMessages={visibleMessages.length > 0}

            />

          </>

        }

      >

        {!initDone || isCreatingSession || isSessionLoading ? (

          <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>

            <CircularProgress />

          </Box>

        ) : (

          <ChatMessageList key={sessionId} messages={visibleMessages} isTyping={sending} />

        )}



        {sendError && (
          <Alert severity="error" onClose={() => setSendError(null)} sx={{ mx: { xs: 1.5, md: 2 }, mb: 1, flexShrink: 0 }}>
            {sendError}
          </Alert>
        )}

        {status === 'ready' && (

          <Alert severity="success" sx={{ mx: { xs: 1.5, md: 2 }, mb: 1, flexShrink: 0 }}>

            Интервью завершено. Запустите TRIZ-анализ — формирование отчёта займёт 1–3 минуты.

          </Alert>

        )}



        {status === 'ready' && (
          <AnalysisProfilePanel onProfileChange={setAnalysisProfile} />
        )}



        {canAnalyze && (

          <Box

            sx={{

              px: { xs: 1.5, md: 2 },

              pb: 1,

              display: 'flex',

              gap: 1,

              flexWrap: 'wrap',

              flexShrink: 0,

            }}

          >

            <Button

              variant="contained"

              startIcon={analyzing ? <CircularProgress size={18} color="inherit" /> : <AnalyticsIcon />}

              disabled={analyzing}

              onClick={handleAnalyze}

              sx={{ minHeight: 44 }}

            >

              Запустить анализ

            </Button>

            <Button

              variant="outlined"

              onClick={handleNewSession}

              disabled={isCreatingSession}

              sx={{ minHeight: 44 }}

            >

              Новый диалог

            </Button>

          </Box>

        )}



        {isAnalyzed ? (

          <Box sx={{ px: { xs: 1.5, md: 2 }, pb: 1, flexShrink: 0 }}>

            <Button variant="contained" onClick={handleOpenReport} fullWidth sx={{ minHeight: 44 }}>

              Открыть отчёт

            </Button>

          </Box>

        ) : (

          <>

            {canForceAnalyze && (
              <Box sx={{ px: { xs: 1.5, md: 2 }, pb: 1, flexShrink: 0 }}>
                <Button
                  variant="outlined"
                  color="secondary"
                  startIcon={<FastForwardIcon />}
                  disabled={analyzing || sending}
                  onClick={handleForceCompleteAndAnalyze}
                  fullWidth
                  sx={{ minHeight: 44 }}
                >
                  Завершить анкету и проанализировать
                </Button>
              </Box>
            )}

            <ChatInput

            disabled={!canSend || !sessionId}

            onSend={handleSend}

            placeholder={

              status === 'ready'

                ? 'Интервью завершено — запустите анализ'

                : 'Введите ответ аналитику…'

            }

          />

          </>

        )}

      </Layout>

    </Box>

  )

}


