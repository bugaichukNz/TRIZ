import { memo, type ReactNode } from 'react'
import Box from '@mui/material/Box'

interface TableScrollWrapperProps {
  children: ReactNode
}

function TableScrollWrapperComponent({ children }: TableScrollWrapperProps) {
  return (
    <Box
      sx={{
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        mx: { xs: -1, sm: 0 },
        px: { xs: 1, sm: 0 },
      }}
    >
      {children}
    </Box>
  )
}

export const TableScrollWrapper = memo(TableScrollWrapperComponent)
