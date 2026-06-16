import { memo } from 'react'
import Box from '@mui/material/Box'
import Step from '@mui/material/Step'
import StepLabel from '@mui/material/StepLabel'
import Stepper from '@mui/material/Stepper'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import type { InterviewBlockStatus } from '../features/chat/interviewProgress'

interface ProgressStepperProps {
  blocks: InterviewBlockStatus[] | null
  sessionStatus?: string
  hasMessages?: boolean
}

function ProgressStepperComponent({ blocks, sessionStatus, hasMessages }: ProgressStepperProps) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))

  if (!blocks || blocks.length === 0) {
    if (hasMessages) return null
    return (
      <Box sx={{ px: 2, py: 0.75 }}>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'inline-block', maxWidth: 360 }}
        >
          Прогресс интервью появится после первых ответов
        </Typography>
      </Box>
    )
  }

  const activeStep = blocks.findIndex((b) => !b.closed)
  const completed =
    sessionStatus === 'ready' || sessionStatus === 'analyzed' || activeStep === -1

  return (
    <Box
      sx={{
        px: 2,
        py: 1,
        overflowX: 'auto',
        overflowY: 'hidden',
        maxWidth: '100%',
      }}
    >
      <Stepper
        activeStep={completed ? blocks.length : Math.max(activeStep, 0)}
        alternativeLabel={!isMobile}
        orientation={isMobile ? 'vertical' : 'horizontal'}
        sx={{
          maxWidth: 720,
          '& .MuiStepLabel-label': {
            fontSize: '0.7rem',
          },
        }}
      >
        {blocks.map((block) => (
          <Step key={block.block} completed={block.closed || completed}>
            <StepLabel
              optional={
                !isMobile ? (
                  <Typography variant="caption" color="text.secondary">
                    {block.closed ? 'готово' : 'в процессе'}
                  </Typography>
                ) : undefined
              }
            >
              {block.block}
            </StepLabel>
          </Step>
        ))}
      </Stepper>
    </Box>
  )
}

export const ProgressStepper = memo(ProgressStepperComponent)
