import { memo } from 'react'
import SmartToyOutlinedIcon from '@mui/icons-material/SmartToyOutlined'
import Avatar from '@mui/material/Avatar'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { ChatMessage as ChatMessageType } from '../../types/triz'
import { chatColors } from '../../theme'

interface ChatMessageProps {
  message: ChatMessageType
}

function ChatMessageComponent({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        alignItems: 'flex-end',
        gap: 1,
      }}
    >
      {!isUser && (
        <Avatar
          sx={{
            width: 32,
            height: 32,
            bgcolor: chatColors.accent,
            flexShrink: 0,
          }}
        >
          <SmartToyOutlinedIcon sx={{ fontSize: 18 }} />
        </Avatar>
      )}
      <Box
        sx={{
          maxWidth: '70%',
          px: 2,
          py: 1.5,
          borderRadius: 2,
          bgcolor: isUser ? chatColors.userBubble : chatColors.analystBubble,
          border: isUser ? `1px solid ${chatColors.userBubbleBorder}` : 'none',
        }}
      >
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', mb: 0.5, fontWeight: 600 }}
        >
          {isUser ? 'Вы' : 'Аналитик'}
        </Typography>
        <Typography
          variant="body1"
          sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
        >
          {message.content}
        </Typography>
      </Box>
    </Box>
  )
}

export const ChatMessage = memo(ChatMessageComponent)
