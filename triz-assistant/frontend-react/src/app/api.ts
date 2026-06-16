import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import { clearAuthSession, getAuthToken } from './authToken'
import type {
  ActiveChatStateResponse,
  AnalyzeProgressResponse,
  AuthUser,
  ChatAnalyzeResponse,
  ChatMessage,
  ChatSession,
  ChatSessionsDeleteResponse,
  ChatSessionsListResponse,
  HealthResponse,
  HistoryEntry,
  LoginResponse,
  SolveRequest,
  SolveResponse,
  TRIZAnalysisResult,
} from '../types/triz'

const baseUrl = import.meta.env.VITE_API_URL ?? ''

const rawBaseQuery = fetchBaseQuery({
  baseUrl,
  prepareHeaders: (headers) => {
    const token = getAuthToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    return headers
  },
})

const baseQuery: typeof rawBaseQuery = async (args, api, extraOptions) => {
  const result = await rawBaseQuery(args, api, extraOptions)
  const requestUrl = typeof args === 'string' ? args : args.url
  const isLoginRequest = requestUrl === '/auth/login'

  if (result.error && result.error.status === 401 && !isLoginRequest) {
    clearAuthSession()
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  }
  return result
}

export function isSessionNotFoundError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  if ('status' in err && (err as { status: number }).status === 404) return true
  if ('data' in err) {
    const detail = String((err as { data?: { detail?: string } }).data?.detail ?? '')
    return /не найдена|not found/i.test(detail)
  }
  return false
}

export const trizApi = createApi({
  reducerPath: 'trizApi',
  baseQuery,
  tagTypes: ['ChatSession', 'ChatSessionList', 'ActiveChat', 'History', 'Report', 'Auth'],
  endpoints: (builder) => ({
    login: builder.mutation<LoginResponse, { username: string; password: string }>({
      query: (body) => ({
        url: '/auth/login',
        method: 'POST',
        body,
      }),
    }),

    getMe: builder.query<AuthUser, void>({
      query: () => '/auth/me',
      providesTags: [{ type: 'Auth', id: 'ME' }],
    }),

    health: builder.query<HealthResponse, void>({
      query: () => '/health',
    }),

    listChatSessions: builder.query<ChatSessionsListResponse, number | void>({
      query: (limit = 20) => `/chat/sessions?limit=${limit}`,
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({ type: 'ChatSessionList' as const, id })),
              { type: 'ChatSessionList', id: 'LIST' },
            ]
          : [{ type: 'ChatSessionList', id: 'LIST' }],
    }),

    getChatSession: builder.query<ChatSession, string>({
      query: (id) => `/chat/sessions/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'ChatSession', id }],
    }),

    createChatSession: builder.mutation<ChatSession, void>({
      query: () => ({
        url: '/chat/sessions',
        method: 'POST',
      }),
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled
          dispatch(trizApi.util.upsertQueryData('getChatSession', data.id, data))
        } catch {
          /* mutation failed */
        }
      },
      invalidatesTags: [
        { type: 'ChatSessionList', id: 'LIST' },
        { type: 'ActiveChat', id: 'CURRENT' },
      ],
    }),

    sendChatMessage: builder.mutation<ChatSession, { sessionId: string; content: string }>({
      query: ({ sessionId, content }) => ({
        url: `/chat/sessions/${sessionId}/messages`,
        method: 'POST',
        body: { content },
      }),
      async onQueryStarted({ sessionId, content }, { dispatch, queryFulfilled }) {
        const trimmed = content.trim()
        let patch: { undo: () => void } | undefined
        // Optimistic UI: сразу добавляем пользовательское сообщение в кеш.
        // Если кеш ещё не инициализирован (редко, но бывает при быстрой навигации),
        // то просто пропускаем оптимизм.
        try {
          patch = dispatch(
            trizApi.util.updateQueryData('getChatSession', sessionId, (draft) => {
              draft.messages.push({ role: 'user', content: trimmed })
            }),
          )
        } catch {
          /* no cache yet */
        }
        try {
          // В теле ответа сервер возвращает обновлённую сессию целиком:
          // включая ответ аналитика в `messages`.
          const { data: freshSession } = await queryFulfilled

          // Обновляем кеш живого запроса так, чтобы UI мгновенно отрендерил fresh `messages`.
          try {
            dispatch(
              trizApi.util.updateQueryData('getChatSession', sessionId, (draft) => {
                Object.assign(draft, freshSession)
              }),
            )
          } catch {
            // Если кеш ещё не был подписан/инициализирован — используем upsert.
            dispatch(trizApi.util.upsertQueryData('getChatSession', sessionId, freshSession))
          }
        } catch {
          patch?.undo()
        }
      },
      invalidatesTags: [{ type: 'ChatSessionList', id: 'LIST' }],
    }),

    completeChatSession: builder.mutation<ChatSession, string>({
      query: (sessionId) => ({
        url: `/chat/sessions/${sessionId}/complete`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, sessionId) => [
        { type: 'ChatSession', id: sessionId },
        { type: 'ChatSessionList', id: 'LIST' },
      ],
    }),

    analyzeChatSession: builder.mutation<
      ChatAnalyzeResponse,
      string | { sessionId: string; force?: boolean }
    >({
      query: (arg) => {
        const sessionId = typeof arg === 'string' ? arg : arg.sessionId
        const force = typeof arg === 'string' ? false : Boolean(arg.force)
        return {
          url: `/chat/sessions/${sessionId}/analyze`,
          method: 'POST',
          body: { force },
        }
      },
      invalidatesTags: (_result, _error, arg) => {
        const sessionId = typeof arg === 'string' ? arg : arg.sessionId
        return [
          { type: 'ChatSession', id: sessionId },
          { type: 'ChatSessionList', id: 'LIST' },
          { type: 'Report', id: sessionId },
          { type: 'History', id: 'LIST' },
        ]
      },
    }),

    getAnalyzeStatus: builder.query<AnalyzeProgressResponse, string>({
      query: (sessionId) => `/chat/sessions/${sessionId}/analyze/status`,
    }),

    deleteChatSession: builder.mutation<ChatSessionsDeleteResponse, string>({
      query: (sessionId) => ({
        url: `/chat/sessions/${sessionId}`,
        method: 'DELETE',
      }),
      invalidatesTags: [{ type: 'ChatSessionList', id: 'LIST' }],
    }),

    deleteAllChatSessions: builder.mutation<ChatSessionsDeleteResponse, void>({
      query: () => ({
        url: '/chat/sessions',
        method: 'DELETE',
      }),
      invalidatesTags: [{ type: 'ChatSessionList', id: 'LIST' }],
    }),

    getActiveChat: builder.query<ActiveChatStateResponse, void>({
      query: () => '/state/active-chat',
      providesTags: [{ type: 'ActiveChat', id: 'CURRENT' }],
    }),

    setActiveChat: builder.mutation<ActiveChatStateResponse, string | null>({
      query: (sessionId) => ({
        url: '/state/active-chat',
        method: 'PUT',
        body: { session_id: sessionId },
      }),
      invalidatesTags: [{ type: 'ActiveChat', id: 'CURRENT' }],
    }),

    solve: builder.mutation<SolveResponse, SolveRequest>({
      query: (body) => ({
        url: '/solve',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'History', id: 'LIST' }],
    }),

    listHistory: builder.query<{ items: HistoryEntry[]; limit: number }, { limit?: number; summary?: boolean } | void>({
      query: (args) => {
        const limit = args?.limit ?? 20
        const summary = args?.summary ?? false
        return `/sessions?limit=${limit}&summary=${summary}`
      },
      providesTags: [{ type: 'History', id: 'LIST' }],
    }),

    getHistoryEntry: builder.query<HistoryEntry, string>({
      query: (id) => `/sessions/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'History', id }],
    }),
  }),
})

export const {
  useLoginMutation,
  useGetMeQuery,
  useHealthQuery,
  useListChatSessionsQuery,
  useGetChatSessionQuery,
  useCreateChatSessionMutation,
  useSendChatMessageMutation,
  useCompleteChatSessionMutation,
  useAnalyzeChatSessionMutation,
  useLazyGetAnalyzeStatusQuery,
  useDeleteChatSessionMutation,
  useDeleteAllChatSessionsMutation,
  useGetActiveChatQuery,
  useSetActiveChatMutation,
  useSolveMutation,
  useListHistoryQuery,
  useGetHistoryEntryQuery,
} = trizApi

/** Видимые сообщения чата (без служебных system/context) */
export function filterVisibleMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.filter((m) => {
    if (m.role === 'system') return false
    if (m.role === 'assistant' && m.content.startsWith('[КОНТЕКСТ:')) return false
    return true
  })
}

export function isTRIZResult(value: unknown): value is TRIZAnalysisResult {
  return (
    typeof value === 'object' &&
    value !== null &&
    'executive_summary' in value &&
    'solution_concepts' in value
  )
}
