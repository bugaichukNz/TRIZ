import { memo, useState } from 'react'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import Badge from '@mui/material/Badge'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import IconButton from '@mui/material/IconButton'
import Step from '@mui/material/Step'
import StepContent from '@mui/material/StepContent'
import StepLabel from '@mui/material/StepLabel'
import Stepper from '@mui/material/Stepper'
import Typography from '@mui/material/Typography'
import type { PipelineStepTrace, PipelineStepStatus } from '../../types/triz'

interface PipelineTimelineProps {
  steps: PipelineStepTrace[]
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} мс`
  return `${(ms / 1000).toFixed(1)} с`
}

function StepStatusIcon({ status, attempts }: { status: PipelineStepStatus; attempts: number }) {
  if (status === 'warning') {
    return <WarningAmberIcon color="warning" sx={{ fontSize: 22 }} />
  }

  const icon = <CheckCircleIcon color="success" sx={{ fontSize: 22 }} />

  if (status === 'ok_with_retries' && attempts > 1) {
    return (
      <Badge
        badgeContent={`${attempts} попыток`}
        color="primary"
        sx={{
          '& .MuiBadge-badge': {
            fontSize: '0.6rem',
            height: 16,
            minWidth: 16,
            px: 0.5,
            right: -8,
            top: 4,
          },
        }}
      >
        {icon}
      </Badge>
    )
  }

  return icon
}

function PipelineStepDetails({ step }: { step: PipelineStepTrace }) {
  return (
    <Box sx={{ pt: 0.5, pb: 1 }}>
      {step.tools_used.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            Инструменты / приёмы
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {step.tools_used.map((tool) => (
              <Chip key={tool} label={tool} size="small" variant="outlined" />
            ))}
          </Box>
        </Box>
      )}
      {step.validator_notes.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            Замечания валидаторов
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {step.validator_notes.map((note, i) => (
              <Typography component="li" key={i} variant="body2" sx={{ mb: 0.5 }}>
                {note}
              </Typography>
            ))}
          </Box>
        </Box>
      )}
      {step.tools_used.length === 0 && step.validator_notes.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Дополнительных деталей нет
        </Typography>
      )}
    </Box>
  )
}

function PipelineTimelineComponent({ steps }: PipelineTimelineProps) {
  const [expandedStep, setExpandedStep] = useState<string | false>(false)

  const handleToggle = (stepId: string) => {
    setExpandedStep((prev) => (prev === stepId ? false : stepId))
  }

  return (
    <Stepper
      activeStep={steps.length}
      orientation="vertical"
      sx={{
        '& .MuiStepConnector-line': {
          minHeight: 16,
        },
      }}
    >
      {steps.map((step) => {
        const isOpen = expandedStep === step.step_id
        return (
          <Step key={step.step_id} completed expanded>
            <StepLabel
              StepIconComponent={() => (
                <StepStatusIcon status={step.status} attempts={step.attempts} />
              )}
              onClick={() => handleToggle(step.step_id)}
              sx={{ cursor: 'pointer', py: 0.5 }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  width: '100%',
                  gap: 1,
                }}
              >
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {step.title}
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">
                    {formatDuration(step.duration_ms)}
                  </Typography>
                  <IconButton
                    size="small"
                    aria-label={isOpen ? 'Свернуть' : 'Развернуть'}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleToggle(step.step_id)
                    }}
                    sx={{
                      transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s',
                    }}
                  >
                    <ExpandMoreIcon fontSize="small" />
                  </IconButton>
                </Box>
              </Box>
            </StepLabel>
            <StepContent>
              <Collapse in={isOpen}>
                <PipelineStepDetails step={step} />
              </Collapse>
            </StepContent>
          </Step>
        )
      })}
    </Stepper>
  )
}

export const PipelineTimeline = memo(PipelineTimelineComponent)
