import { memo, useCallback, useState, type KeyboardEvent } from 'react'
import SendIcon from '@mui/icons-material/Send'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import TextField from '@mui/material/TextField'

interface ChatInputProps {
  disabled?: boolean
  onSend: (text: string) => void
  placeholder?: string
}

function ChatInputComponent({
  disabled,
  onSend,
  placeholder = 'Введите ответ…',
}: ChatInputProps) {
  const [text, setText] = useState('')

  const submit = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }, [text, disabled, onSend])

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <Box
      sx={{
        flexShrink: 0,
        px: { xs: 1.5, md: 2 },
        pt: 1.5,
        pb: 'max(12px, env(safe-area-inset-bottom))',
        bgcolor: 'background.default',
        boxShadow: '0 -1px 3px rgba(0, 0, 0, 0.06)',
      }}
    >
      <Box
        component="form"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        sx={{
          maxWidth: 760,
          mx: 'auto',
          display: 'flex',
          alignItems: 'flex-end',
          gap: 0.5,
          p: 0.75,
          pl: 1.5,
          bgcolor: 'background.paper',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 3,
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
        }}
      >
        <TextField
          fullWidth
          multiline
          maxRows={6}
          variant="standard"
          placeholder={placeholder}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          slotProps={{
            input: {
              disableUnderline: true,
              sx: { fontSize: '0.95rem', py: 1, minHeight: 44 },
            },
          }}
        />
        <IconButton
          type="submit"
          disabled={disabled || !text.trim()}
          aria-label="Отправить"
          sx={{
            width: 44,
            height: 44,
            flexShrink: 0,
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            '&:hover': {
              bgcolor: 'primary.dark',
            },
            '&.Mui-disabled': {
              bgcolor: 'action.disabledBackground',
              color: 'action.disabled',
            },
          }}
        >
          <SendIcon fontSize="small" />
        </IconButton>
      </Box>
    </Box>
  )
}

export const ChatInput = memo(ChatInputComponent)
