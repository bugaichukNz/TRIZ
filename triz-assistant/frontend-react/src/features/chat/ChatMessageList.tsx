import { memo, useEffect, useRef } from 'react'
import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { ChatMessage as ChatMessageType } from '../../types/triz'
import { TypingIndicator } from '../../components/TypingIndicator'
import { ChatMessage } from './ChatMessage'

interface ChatMessageListProps {
  messages: ChatMessageType[]
  isTyping?: boolean
}

function ChatMessageListComponent({ messages, isTyping }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  const isEmpty = messages.length === 0 && !isTyping

  return (
    <Box
      ref={listRef}
      sx={{
        flex: 1,
        minHeight: 0,
        overflowY: 'auto',
        overflowX: 'hidden',
        px: { xs: 1.5, md: 2 },
        py: 2,
      }}
    >
      <Box
        sx={{
          maxWidth: 760,
          mx: 'auto',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
          minHeight: isEmpty ? '100%' : undefined,
          justifyContent: isEmpty ? 'center' : undefined,
        }}
      >
        {isEmpty && (
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 1.5,
              py: 6,
              color: 'text.secondary',
            }}
          >
            <ForumOutlinedIcon sx={{ fontSize: 48, opacity: 0.35 }} />
            <Typography variant="body1" sx={{ textAlign: 'center' }}>
              Начните диалог — аналитик задаст первый вопрос
            </Typography>
            <Typography variant="body2" sx={{ textAlign: 'center' }} color="text.secondary">
              Опишите задачу в поле ввода ниже
            </Typography>
          </Box>
        )}

        {messages.map((msg, idx) => (
          <ChatMessage key={`${idx}-${msg.role}-${msg.content.slice(0, 32)}`} message={msg} />
        ))}

        {isTyping && (
          <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1 }}>
            <Box
              sx={{
                px: 2,
                py: 1,
                borderRadius: 2,
                bgcolor: 'background.paper',
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <TypingIndicator />
            </Box>
          </Box>
        )}
        <div ref={bottomRef} />
      </Box>
    </Box>
  )
}

export const ChatMessageList = memo(ChatMessageListComponent)
