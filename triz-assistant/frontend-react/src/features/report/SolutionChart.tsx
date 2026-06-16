import { memo, useMemo } from 'react'
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { SolutionConcept } from '../../types/triz'
import { computeTotalScore } from '../../types/triz'

interface SolutionChartProps {
  solutions: SolutionConcept[]
}

function SolutionChartComponent({ solutions }: SolutionChartProps) {
  const data = useMemo(
    () =>
      solutions.map((s) => ({
        id: s.id,
        name: s.title,
        effectiveness: s.effectiveness_score,
        complexity: s.complexity_score,
        total: computeTotalScore(s),
      })),
    [solutions],
  )

  if (data.length === 0) return null

  return (
    <Box sx={{ width: '100%', height: 320, mt: 1 }}>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        Эффективность vs сложность (размер точки — итоговый балл)
      </Typography>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 16, right: 24, bottom: 24, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E5E5" />
          <XAxis
            type="number"
            dataKey="complexity"
            name="Сложность"
            domain={[0, 10]}
            label={{ value: 'Сложность', position: 'insideBottom', offset: -8 }}
          />
          <YAxis
            type="number"
            dataKey="effectiveness"
            name="Эффективность"
            domain={[0, 10]}
            label={{ value: 'Эффективность', angle: -90, position: 'insideLeft' }}
          />
          <ZAxis type="number" dataKey="total" range={[80, 400]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            labelFormatter={(_, payload) => {
              const item = payload?.[0]?.payload as { name?: string; id?: number } | undefined
              return item ? `#${item.id} ${item.name}` : ''
            }}
          />
          <Scatter data={data} fill="#1F3964" />
        </ScatterChart>
      </ResponsiveContainer>
    </Box>
  )
}

export const SolutionChart = memo(SolutionChartComponent)
