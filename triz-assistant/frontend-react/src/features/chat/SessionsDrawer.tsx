import { memo } from 'react'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import Typography from '@mui/material/Typography'
import type { ChatSessionSummary } from '../../types/triz'

const DRAWER_WIDTH = 280

interface SessionsDrawerProps {
  open: boolean
  variant: 'permanent' | 'temporary'
  onClose: () => void
  sessions: ChatSessionSummary[]
  activeSessionId: string | null
  onSelect: (id: string) => void
  onNew: () => void | Promise<void>
  onDelete: (id: string) => void
  isLoading?: boolean
  isCreating?: boolean
}

const statusLabel: Record<string, string> = {
  interview: 'Интервью',
  ready: 'Готово',
  analyzed: 'Анализ',
}

const statusColor: Record<string, 'default' | 'success' | 'primary'> = {
  interview: 'default',
  ready: 'success',
  analyzed: 'primary',
}

function SessionCard({
  session,
  isActive,
  onSelect,
  onDelete,
  onCloseDrawer,
  isTemporary,
}: {
  session: ChatSessionSummary
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
  onCloseDrawer: () => void
  isTemporary: boolean
}) {
  return (
    <Box
      onClick={() => {
        onSelect()
        if (isTemporary) onCloseDrawer()
      }}
      sx={{
        position: 'relative',
        mx: 1,
        mb: 0.75,
        px: 1.5,
        py: 1.25,
        borderRadius: 1.5,
        cursor: 'pointer',
        border: '1px solid',
        borderColor: isActive ? 'primary.main' : 'divider',
        bgcolor: isActive ? 'rgba(31, 57, 100, 0.06)' : 'background.paper',
        transition: 'background-color 0.15s, border-color 0.15s',
        '&::before': isActive
          ? {
              content: '""',
              position: 'absolute',
              left: 0,
              top: 8,
              bottom: 8,
              width: 3,
              borderRadius: '0 2px 2px 0',
              bgcolor: 'primary.main',
            }
          : undefined,
        '&:hover': {
          bgcolor: isActive ? 'rgba(31, 57, 100, 0.08)' : 'action.hover',
          '& .session-delete': {
            opacity: 1,
          },
        },
        '@media (hover: none)': {
          '& .session-delete': {
            opacity: 1,
          },
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        <Box sx={{ flex: 1, minWidth: 0, pl: isActive ? 0.5 : 0 }}>
          <Typography variant="subtitle2" noWrap sx={{ fontWeight: 600, mb: 0.25 }}>
            {session.title || 'Без названия'}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            {new Date(session.updated_at).toLocaleString('ru-RU', {
              day: 'numeric',
              month: 'short',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Typography>
        </Box>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            flexShrink: 0,
          }}
        >
          <Chip
            label={statusLabel[session.status] ?? session.status}
            size="small"
            color={statusColor[session.status] ?? 'default'}
            variant="outlined"
            sx={{ height: 24, fontSize: '0.7rem' }}
          />
          <IconButton
            className="session-delete"
            size="small"
            aria-label="Удалить диалог"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            sx={{
              opacity: 0,
              transition: 'opacity 0.15s',
              width: 36,
              height: 36,
            }}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>
    </Box>
  )
}

function SessionsDrawerComponent({
  open,
  variant,
  onClose,
  sessions,
  activeSessionId,
  onSelect,
  onNew,
  onDelete,
  isLoading,
  isCreating,
}: SessionsDrawerProps) {
  const content = (
    <Box
      sx={{
        width: DRAWER_WIDTH,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.paper',
        overflow: 'hidden',
      }}
    >
      <Box sx={{ p: 2, pb: 1.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1.5 }}>
          Диалоги
        </Typography>
        <Button
          variant="contained"
          fullWidth
          startIcon={<AddIcon />}
          onClick={() => void onNew()}
          disabled={isCreating}
          sx={{ minHeight: 44 }}
        >
          {isCreating ? 'Создание…' : 'Новый диалог'}
        </Button>
      </Box>
      <Divider />
      <List sx={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', py: 1, px: 0 }}>
        {sessions.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            {isLoading ? 'Загрузка…' : 'Нет сохранённых диалогов'}
          </Typography>
        )}
        {sessions.map((session) => (
          <SessionCard
            key={session.id}
            session={session}
            isActive={session.id === activeSessionId}
            onSelect={() => onSelect(session.id)}
            onDelete={() => onDelete(session.id)}
            onCloseDrawer={onClose}
            isTemporary={variant === 'temporary'}
          />
        ))}
      </List>
    </Box>
  )

  if (variant === 'permanent') {
    return (
      <Box
        component="aside"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          height: '100%',
          borderRight: '1px solid',
          borderColor: 'divider',
          overflow: 'hidden',
        }}
      >
        {content}
      </Box>
    )
  }

  return (
    <Drawer
      variant="temporary"
      open={open}
      onClose={onClose}
      ModalProps={{ keepMounted: true }}
      sx={{
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
        },
      }}
    >
      {content}
    </Drawer>
  )
}

export const SessionsDrawer = memo(SessionsDrawerComponent)
export { DRAWER_WIDTH }
