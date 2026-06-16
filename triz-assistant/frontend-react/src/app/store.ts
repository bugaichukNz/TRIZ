import { configureStore } from '@reduxjs/toolkit'
import { useDispatch } from 'react-redux'
import { trizApi } from './api'

export const store = configureStore({
  reducer: {
    [trizApi.reducerPath]: trizApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(trizApi.middleware),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch

export const useAppDispatch = () => useDispatch<AppDispatch>()
