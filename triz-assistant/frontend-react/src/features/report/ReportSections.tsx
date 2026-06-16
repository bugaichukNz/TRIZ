import { memo, useState, type ReactNode } from 'react'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import type { TRIZAnalysisResult } from '../../types/triz'
import { computeTotalScore } from '../../types/triz'
import { TableScrollWrapper } from '../../components/TableScrollWrapper'
import { SolutionChart } from './SolutionChart'

interface ReportSectionsProps {
  result: TRIZAnalysisResult
  brief?: string
}

interface LazyAccordionProps {
  title: string
  defaultExpanded?: boolean
  children: ReactNode
}

function LazyAccordion({ title, defaultExpanded = false, children }: LazyAccordionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [mounted, setMounted] = useState(defaultExpanded)

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, isExpanded) => {
        setExpanded(isExpanded)
        if (isExpanded) setMounted(true)
      }}
      disableGutters
      elevation={0}
      sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 1 }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 48 }}>
        <Typography sx={{ fontWeight: 600 }}>{title}</Typography>
      </AccordionSummary>
      <AccordionDetails>{mounted ? children : null}</AccordionDetails>
    </Accordion>
  )
}

function ListItems({ items }: { items: string[] }) {
  if (!items.length) return <Typography color="text.secondary">—</Typography>
  return (
    <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
      {items.map((item, i) => (
        <Typography component="li" key={i} variant="body2" sx={{ mb: 0.5 }}>
          {item}
        </Typography>
      ))}
    </Box>
  )
}

function ReportSectionsComponent({ result, brief }: ReportSectionsProps) {
  const sc = result.system_context

  return (
    <Box>
      <Paper
        sx={{
          p: { xs: 2, md: 3 },
          mb: 3,
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
          border: 'none',
        }}
      >
        <Typography variant="overline" sx={{ opacity: 0.85 }}>
          Executive summary
        </Typography>
        <Typography variant="h2" sx={{ fontSize: { xs: '1.1rem', md: '1.25rem' }, mt: 0.5, fontWeight: 500 }}>
          {result.executive_summary}
        </Typography>
      </Paper>

      {brief && (
        <LazyAccordion title="Исходный бриф интервью">
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {brief}
          </Typography>
        </LazyAccordion>
      )}

      <LazyAccordion title="Описание задачи" defaultExpanded>
        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
          {result.problem_description}
        </Typography>
        {result.assumptions.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Допущения
            </Typography>
            <ListItems items={result.assumptions} />
          </Box>
        )}
        {result.root_cause && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Корневая причина (ПСА)
            </Typography>
            <Typography variant="body2">{result.root_cause}</Typography>
          </Box>
        )}
      </LazyAccordion>

      <LazyAccordion title="Система и надсистема">
        <TableScrollWrapper>
          <Table size="small" sx={{ minWidth: 480 }}>
            <TableBody>
              {[
                ['Система', sc.system],
                ['Надсистема', sc.supersystem],
                ['Подсистемы', sc.subsystems.join('; ') || '—'],
                ['Полезные функции', sc.useful_functions.join('; ') || '—'],
                ['Нежелательные эффекты', sc.harmful_effects.join('; ') || '—'],
                ['Ограничения', sc.constraints.join('; ') || '—'],
                ['Ресурсы', sc.resources.join('; ') || '—'],
              ].map(([label, value]) => (
                <TableRow key={label}>
                  <TableCell sx={{ fontWeight: 600, width: '35%', verticalAlign: 'top' }}>
                    {label}
                  </TableCell>
                  <TableCell>{value}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableScrollWrapper>
      </LazyAccordion>

      <LazyAccordion title="Противоречия и ИКР">
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Chip label="ТП" size="small" color="primary" sx={{ mb: 1 }} />
            <Typography variant="body2">{result.technical_contradiction}</Typography>
          </Box>
          <Box>
            <Chip label="ФП" size="small" color="primary" variant="outlined" sx={{ mb: 1 }} />
            <Typography variant="body2">{result.physical_contradiction}</Typography>
          </Box>
          <Box>
            <Chip label="Тип" size="small" sx={{ mb: 1 }} />
            <Typography variant="body2">{result.contradiction_type}</Typography>
          </Box>
          <Box>
            <Chip label="ИКР" size="small" color="secondary" sx={{ mb: 1 }} />
            <Typography variant="body2">{result.ideal_final_result}</Typography>
          </Box>
        </Box>
      </LazyAccordion>

      <LazyAccordion title="Анализ">
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {(
            [
              ['Причинно-следственные цепочки', result.analysis.causal_chains],
              ['Функциональный анализ', result.analysis.functional_analysis],
              ['Ресурсы', result.analysis.resources_analysis],
              ['Зоны противоречий', result.analysis.contradiction_zones],
            ] as const
          ).map(([title, text]) => (
            <Box key={title}>
              <Typography variant="subtitle2" gutterBottom>
                {title}
              </Typography>
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                {text}
              </Typography>
            </Box>
          ))}
        </Box>
      </LazyAccordion>

      <LazyAccordion title="Применённые инструменты ТРИЗ">
        <TableScrollWrapper>
          <Table size="small" sx={{ minWidth: 640 }}>
            <TableHead>
              <TableRow>
                <TableCell>Инструмент</TableCell>
                <TableCell>Зачем</TableCell>
                <TableCell>Инсайт</TableCell>
                <TableCell>Практическая ценность</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {result.triz_tools.map((row, i) => (
                <TableRow key={i}>
                  <TableCell sx={{ fontWeight: 500 }}>{row.tool}</TableCell>
                  <TableCell>{row.why_applied}</TableCell>
                  <TableCell>{row.insight}</TableCell>
                  <TableCell>{row.practical_value}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableScrollWrapper>
      </LazyAccordion>

      <LazyAccordion title="Решения">
        <TableScrollWrapper>
          <Table size="small" sx={{ minWidth: 720 }}>
            <TableHead>
              <TableRow>
                <TableCell>#</TableCell>
                <TableCell>Название</TableCell>
                <TableCell>Принцип</TableCell>
                <TableCell>Механизм</TableCell>
                <TableCell>Применимость</TableCell>
                <TableCell>Риски</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {result.solution_concepts.map((sol) => (
                <TableRow key={sol.id}>
                  <TableCell>{sol.id}</TableCell>
                  <TableCell sx={{ fontWeight: 500 }}>{sol.title}</TableCell>
                  <TableCell>{sol.triz_principle}</TableCell>
                  <TableCell>{sol.mechanism}</TableCell>
                  <TableCell>{sol.applicability}</TableCell>
                  <TableCell>{sol.risks}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableScrollWrapper>
      </LazyAccordion>

      <LazyAccordion title="Сравнение решений">
        <TableScrollWrapper>
          <Table size="small" sx={{ minWidth: 560, mb: 2 }}>
            <TableHead>
              <TableRow>
                <TableCell>#</TableCell>
                <TableCell>Решение</TableCell>
                <TableCell align="right">Эффект.</TableCell>
                <TableCell align="right">Сложн.</TableCell>
                <TableCell align="right">Стоим.</TableCell>
                <TableCell align="right">Масшт.</TableCell>
                <TableCell align="right">Итого</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {result.solution_concepts.map((sol) => (
                <TableRow key={sol.id}>
                  <TableCell>{sol.id}</TableCell>
                  <TableCell>{sol.title}</TableCell>
                  <TableCell align="right">{sol.effectiveness_score}</TableCell>
                  <TableCell align="right">{sol.complexity_score}</TableCell>
                  <TableCell align="right">{sol.cost_score}</TableCell>
                  <TableCell align="right">{sol.scalability_score}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    {computeTotalScore(sol)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableScrollWrapper>
        <SolutionChart solutions={result.solution_concepts} />
      </LazyAccordion>

      <LazyAccordion title="Рекомендации">
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Typography variant="subtitle2">Приоритеты</Typography>
            <ListItems items={result.recommendations.priorities} />
          </Box>
          <Typography variant="body2">
            Приоритетное решение: #{result.recommendations.priority_solution_id}
          </Typography>
          <Box>
            <Typography variant="subtitle2">Быстрые проверки</Typography>
            <ListItems items={result.recommendations.quick_checks} />
          </Box>
          <Box>
            <Typography variant="subtitle2">MVP / пилоты</Typography>
            <ListItems items={result.recommendations.mvp_pilots} />
          </Box>
          <Box>
            <Typography variant="subtitle2">Критические риски</Typography>
            <ListItems items={result.recommendations.critical_risks} />
          </Box>
          <Box>
            <Typography variant="subtitle2">Эксперименты</Typography>
            <ListItems items={result.recommendations.experiments} />
          </Box>
          <Box>
            <Typography variant="subtitle2">Метрики</Typography>
            <ListItems items={result.recommendations.metrics} />
          </Box>
          {result.recommended_principles.length > 0 && (
            <Box>
              <Typography variant="subtitle2">Принципы ТРИЗ</Typography>
              <ListItems items={result.recommended_principles} />
            </Box>
          )}
        </Box>
      </LazyAccordion>

      <LazyAccordion title="Итоговый вывод">
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Typography variant="subtitle2">Рекомендуемое решение</Typography>
            <Typography variant="body2">{result.final_conclusion.recommended_solution}</Typography>
          </Box>
          <Box>
            <Typography variant="subtitle2">Ключевой риск</Typography>
            <Typography variant="body2">{result.final_conclusion.key_risk}</Typography>
          </Box>
          <Box>
            <Typography variant="subtitle2">Следующий шаг</Typography>
            <Typography variant="body2">{result.final_conclusion.next_step}</Typography>
          </Box>
        </Box>
      </LazyAccordion>
    </Box>
  )
}

export const ReportSections = memo(ReportSectionsComponent)
