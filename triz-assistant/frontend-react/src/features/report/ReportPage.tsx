import { useMemo } from 'react'
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Container from '@mui/material/Container'
import Typography from '@mui/material/Typography'
import { isTRIZResult, useListHistoryQuery } from '../../app/api'
import { getAuthToken } from '../../app/authToken'
import { Layout } from '../../components/Layout'
import type { TRIZAnalysisResult } from '../../types/triz'
import { ReportSections } from './ReportSections'
import { PipelineTimeline } from './PipelineTimeline'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'

interface ReportLocationState {
  brief?: string
  result?: TRIZAnalysisResult
}

const baseUrl = import.meta.env.VITE_API_URL ?? ''

async function downloadReport(path: string, fallbackName: string) {
  const token = getAuthToken()
  const response = await fetch(`${baseUrl}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new Error('Не удалось скачать файл')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition')
  const match = disposition?.match(/filename="?([^"]+)"?/)
  const filename = match?.[1] ?? fallbackName
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function ReportPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const navState = location.state as ReportLocationState | null

  const { data: history, isLoading } = useListHistoryQuery(
    { limit: 50, summary: false },
    { skip: Boolean(navState?.result) },
  )

  const fromHistory = useMemo(() => {
    if (!sessionId || !history?.items) return null
    const entry = history.items.find((item) => item.chat_session_id === sessionId)
    if (!entry || !isTRIZResult(entry.result)) return null
    return { brief: entry.problem, result: entry.result, entryId: entry.id }
  }, [history, sessionId])

  const report = navState?.result
    ? { brief: navState.brief, result: navState.result, entryId: null as string | null }
    : fromHistory

  const handleDownloadHtml = () => {
    if (!sessionId) return
    void downloadReport(
      `/chat/sessions/${sessionId}/report.html`,
      `triz_report_${sessionId.slice(0, 8)}.html`,
    )
  }

  const handleDownloadDocx = () => {
    if (!sessionId) return
    void downloadReport(
      `/chat/sessions/${sessionId}/report.docx`,
      `triz_report_${sessionId.slice(0, 8)}.docx`,
    )
  }

  return (
    <Box sx={{ height: '100dvh', overflow: 'hidden', display: 'flex' }}>
    <Layout
      title="TRIZ-отчёт"
      actions={
        <Button
          component={RouterLink}
          to="/"
          startIcon={<ArrowBackIcon />}
          size="small"
          sx={{ minHeight: 44 }}
        >
          К интервью
        </Button>
      }
    >
      <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
      <Container maxWidth="lg" sx={{ py: { xs: 2, md: 3 }, px: { xs: 1.5, md: 3 } }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Экспертный TRIZ-аналитический отчёт
        </Typography>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Button
            variant="outlined"
            onClick={handleDownloadHtml}
            disabled={!report}
            sx={{ minHeight: 44 }}
          >
            Скачать HTML
          </Button>
          <Button
            variant="outlined"
            onClick={handleDownloadDocx}
            disabled={!report}
            sx={{ minHeight: 44 }}
          >
            Скачать DOCX
          </Button>
        </Box>

        {isLoading && !report && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        )}

        {!isLoading && !report && (
          <Box sx={{ textAlign: 'center', py: 6 }}>
            <Typography gutterBottom>Отчёт для этой сессии не найден.</Typography>
            <Button variant="contained" onClick={() => navigate('/')} sx={{ mt: 2, minHeight: 44 }}>
              Вернуться к интервью
            </Button>
          </Box>
        )}

        {report && (
          <>
            {report.result.pipeline_trace && report.result.pipeline_trace.length > 0 && (
              <Accordion
                defaultExpanded={false}
                disableGutters
                elevation={0}
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  '&:before': { display: 'none' },
                  mb: 2,
                }}
              >
                <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 48 }}>
                  <Typography sx={{ fontWeight: 600 }}>Ход анализа</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <PipelineTimeline steps={report.result.pipeline_trace} />
                </AccordionDetails>
              </Accordion>
            )}
            <ReportSections result={report.result} brief={report.brief} />
          </>
        )}
      </Container>
      </Box>
    </Layout>
    </Box>
  )
}

