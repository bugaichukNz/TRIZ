import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useLoginMutation } from '../../app/api'
import { setAuthSession } from '../../app/authToken'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [login, { isLoading, error }] = useLoginMutation()

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    try {
      const result = await login({ username, password }).unwrap()
      setAuthSession(result.access_token, result.user)
      navigate(from, { replace: true })
    } catch {
      /* shown via error state */
    }
  }

  const errorMessage = (() => {
    if (!error) return null
    if ('status' in error && error.status === 'FETCH_ERROR') {
      return 'Сервер недоступен. Запустите бэкенд: uvicorn backend.main:app --port 8000'
    }
    if ('data' in error) {
      return String((error as { data?: { detail?: string } }).data?.detail ?? 'Ошибка входа')
    }
    return 'Ошибка входа'
  })()

  return (
    <Box
      sx={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Container maxWidth="xs">
        <Paper elevation={2} sx={{ p: { xs: 3, sm: 4 }, borderRadius: 2 }}>
          <Typography variant="h5" component="h1" gutterBottom sx={{ fontWeight: 600 }}>
            TRIZ AI-Ассистент
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Войдите в личный кабинет
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
            Тестовый аккаунт: логин <strong>user</strong>, пароль <strong>user</strong>
          </Typography>

          <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="Логин"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              fullWidth
            />
            <TextField
              label="Пароль"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              fullWidth
            />
            {errorMessage && <Alert severity="error">{errorMessage}</Alert>}
            <Button type="submit" variant="contained" size="large" disabled={isLoading} sx={{ minHeight: 44, mt: 1 }}>
              {isLoading ? 'Вход…' : 'Войти'}
            </Button>
          </Box>
        </Paper>
      </Container>
    </Box>
  )
}
