import Box from '@mui/material/Box'
import LinearProgress from '@mui/material/LinearProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'

interface AnalysisProgressOverlayProps {
  progress: number
  stage: string
}

export function AnalysisProgressOverlay({ progress, stage }: AnalysisProgressOverlayProps) {
  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        zIndex: (theme) => theme.zIndex.modal + 1,
        bgcolor: 'rgba(0,0,0,0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
      }}
    >
      <Paper
        elevation={8}
        sx={{
          width: '100%',
          maxWidth: 420,
          p: 3,
          borderRadius: 2,
        }}
      >
        <Typography variant="h6" gutterBottom>
          Формирование TRIZ-отчёта
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2, minHeight: 40 }}>
          {stage}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{ flex: 1 }}>
            <LinearProgress variant="determinate" value={progress} sx={{ height: 8, borderRadius: 4 }} />
          </Box>
          <Typography variant="body2" sx={{ minWidth: 40, textAlign: 'right', fontWeight: 600 }}>
            {progress}%
          </Typography>
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
          Обычно занимает 1–3 минуты
        </Typography>
      </Paper>
    </Box>
  )
}
