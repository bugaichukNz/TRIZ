import { memo, type ReactNode } from 'react'
import MenuIcon from '@mui/icons-material/Menu'
import LogoutIcon from '@mui/icons-material/Logout'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import Toolbar from '@mui/material/Toolbar'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useNavigate } from 'react-router-dom'
import { clearAuthSession, getAuthUser } from '../app/authToken'
import type { ChatSessionStatus } from '../types/triz'

const statusLabel: Record<ChatSessionStatus, string> = {
  interview: 'Интервью',
  ready: 'Готово',
  analyzed: 'Анализ',
}

const statusColor: Record<ChatSessionStatus, 'default' | 'success' | 'primary'> = {
  interview: 'default',
  ready: 'success',
  analyzed: 'primary',
}

interface LayoutProps {
  title?: string
  sessionTitle?: string | null
  sessionStatus?: ChatSessionStatus
  onMenuClick?: () => void
  actions?: ReactNode
  headerExtra?: ReactNode
  children: ReactNode
}

function LayoutComponent({
  title,
  sessionTitle,
  sessionStatus = 'interview',
  onMenuClick,
  actions,
  headerExtra,
  children,
}: LayoutProps) {
  const navigate = useNavigate()
  const authUser = getAuthUser()
  const isReportLayout = Boolean(title)

  const handleLogout = () => {
    clearAuthSession()
    navigate('/login', { replace: true })
  }
  return (
    <Box
      sx={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        bgcolor: 'background.default',
      }}
    >
      <AppBar
        position="static"
        elevation={0}
        sx={{
          bgcolor: 'background.paper',
          color: 'text.primary',
          borderBottom: '1px solid',
          borderColor: 'divider',
          flexShrink: 0,
        }}
      >
        <Toolbar sx={{ minHeight: { xs: 56, sm: 64 }, gap: 1, flexWrap: 'wrap', py: 1 }}>
          {onMenuClick && (
            <IconButton edge="start" onClick={onMenuClick} aria-label="Меню диалогов">
              <MenuIcon />
            </IconButton>
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {isReportLayout ? (
              <Typography variant="subtitle1" component="h1" sx={{ fontWeight: 600 }}>
                {title}
              </Typography>
            ) : (
              <>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: 'block', lineHeight: 1.4 }}
                >
                  TRIZ-интервью
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Typography
                    variant="subtitle1"
                    component="h1"
                    noWrap
                    sx={{ fontWeight: 600, maxWidth: { xs: 180, sm: 400 } }}
                  >
                    {sessionTitle || 'Новый диалог'}
                  </Typography>
                  <Chip
                    label={statusLabel[sessionStatus]}
                    size="small"
                    color={statusColor[sessionStatus]}
                    variant="outlined"
                    sx={{ height: 24 }}
                  />
                </Box>
              </>
            )}
          </Box>
          {authUser && (
            <Tooltip title={`${authUser.username} · Выйти`}>
              <IconButton onClick={handleLogout} aria-label="Выйти" size="small">
                <LogoutIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {actions}
        </Toolbar>
        {headerExtra}
      </AppBar>
      <Box
        component="main"
        sx={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

export const Layout = memo(LayoutComponent)
