import { useCallback, useEffect, useMemo, useState } from 'react'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import FormControlLabel from '@mui/material/FormControlLabel'
import Slider from '@mui/material/Slider'
import Switch from '@mui/material/Switch'
import Typography from '@mui/material/Typography'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { getAuthToken } from '../../app/authToken'
import type { AnalysisProfile, ToolRegistryItem } from '../../types/triz'

const baseUrl = import.meta.env.VITE_API_URL ?? ''

interface AnalysisProfileRegistryResponse {
  tools: ToolRegistryItem[]
  default_profile: AnalysisProfile
}

function profilesEqual(a: AnalysisProfile, b: AnalysisProfile): boolean {
  const toolKeys = Object.keys(a.tools_enabled).sort()
  const toolKeysB = Object.keys(b.tools_enabled).sort()
  if (toolKeys.join() !== toolKeysB.join()) return false
  for (const key of toolKeys) {
    if (a.tools_enabled[key] !== b.tools_enabled[key]) return false
  }
  return (
    a.effects_rag === b.effects_rag &&
    a.target_solutions === b.target_solutions &&
    a.psa_fp_validation === b.psa_fp_validation
  )
}

interface AnalysisProfilePanelProps {
  onProfileChange: (profile: AnalysisProfile | undefined) => void
}

export function AnalysisProfilePanel({ onProfileChange }: AnalysisProfilePanelProps) {
  const [registry, setRegistry] = useState<AnalysisProfileRegistryResponse | null>(null)
  const [profile, setProfile] = useState<AnalysisProfile | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    const token = getAuthToken()
    void fetch(`${baseUrl}/analysis/profile/registry`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(async (res) => {
        if (!res.ok) throw new Error('Не удалось загрузить реестр профиля')
        return res.json() as Promise<AnalysisProfileRegistryResponse>
      })
      .then((data) => {
        setRegistry(data)
        setProfile(data.default_profile)
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : 'Ошибка загрузки профиля')
      })
  }, [])

  const isCustom = useMemo(() => {
    if (!registry || !profile) return false
    return !profilesEqual(profile, registry.default_profile)
  }, [registry, profile])

  useEffect(() => {
    if (!profile || !registry) return
    onProfileChange(isCustom ? profile : undefined)
  }, [profile, registry, isCustom, onProfileChange])

  const updateProfile = useCallback((patch: Partial<AnalysisProfile>) => {
    setProfile((prev) => (prev ? { ...prev, ...patch } : prev))
  }, [])

  const toggleTool = useCallback((key: string, enabled: boolean) => {
    setProfile((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        tools_enabled: { ...prev.tools_enabled, [key]: enabled },
      }
    })
  }, [])

  if (loadError) {
    return (
      <Alert severity="warning" sx={{ mx: { xs: 1.5, md: 2 }, mb: 1, flexShrink: 0 }}>
        {loadError}
      </Alert>
    )
  }

  if (!registry || !profile) return null

  const basicTools = registry.tools.filter((t) => t.category === 'базовый')
  const optionalTools = registry.tools.filter((t) => t.category === 'опциональный')

  const summaryLabel = isCustom
    ? 'Параметры анализа (нестандартный профиль)'
    : 'Параметры анализа (по умолчанию: стандартный)'

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, open) => setExpanded(open)}
      disableGutters
      elevation={0}
      sx={{
        mx: { xs: 1.5, md: 2 },
        mb: 1,
        flexShrink: 0,
        border: '1px solid',
        borderColor: 'divider',
        '&:before': { display: 'none' },
      }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 48 }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {summaryLabel}
        </Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
          Базовые инструменты
        </Typography>
        {basicTools.map((tool) => (
          <ToolToggle
            key={tool.key}
            tool={tool}
            enabled={profile.tools_enabled[tool.key] ?? false}
            onChange={(v) => toggleTool(tool.key, v)}
          />
        ))}

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', mt: 2, mb: 1.5 }}
        >
          Опциональные инструменты
        </Typography>
        {optionalTools.map((tool) => (
          <ToolToggle
            key={tool.key}
            tool={tool}
            enabled={profile.tools_enabled[tool.key] ?? false}
            onChange={(v) => toggleTool(tool.key, v)}
          />
        ))}

        <Box sx={{ mt: 2 }}>
          <FormControlLabel
            control={
              <Switch
                checked={profile.effects_rag}
                onChange={(_, checked) => updateProfile({ effects_rag: checked })}
              />
            }
            label="Подбор физэффектов (RAG)"
          />
          <FormControlLabel
            control={
              <Switch
                checked={profile.psa_fp_validation}
                onChange={(_, checked) => updateProfile({ psa_fp_validation: checked })}
              />
            }
            label="Валидация ПСА / физического противоречия"
          />
        </Box>

        <Box sx={{ mt: 2, px: 1 }}>
          <Typography variant="body2" gutterBottom>
            Число решений: {profile.target_solutions}
          </Typography>
          <Slider
            value={profile.target_solutions}
            min={2}
            max={8}
            step={1}
            marks
            valueLabelDisplay="auto"
            onChange={(_, value) =>
              updateProfile({ target_solutions: value as number })
            }
          />
        </Box>
      </AccordionDetails>
    </Accordion>
  )
}

function ToolToggle({
  tool,
  enabled,
  onChange,
}: {
  tool: ToolRegistryItem
  enabled: boolean
  onChange: (enabled: boolean) => void
}) {
  return (
    <Box sx={{ mb: 1 }}>
      <FormControlLabel
        control={<Switch checked={enabled} onChange={(_, v) => onChange(v)} />}
        label={
          <Box>
            <Typography variant="body2">{tool.title}</Typography>
            <Typography variant="caption" color="text.secondary">
              {tool.description}
            </Typography>
          </Box>
        }
        sx={{ alignItems: 'flex-start', ml: 0 }}
      />
      {!enabled && tool.warning_if_disabled && (
        <Alert severity="warning" sx={{ mt: 0.5, py: 0 }}>
          <Typography variant="caption">{tool.warning_if_disabled}</Typography>
        </Alert>
      )}
    </Box>
  )
}

export function describeProfileDeviations(
  profile: AnalysisProfile,
  defaultProfile: AnalysisProfile,
): string[] {
  const notes: string[] = []
  for (const [key, enabled] of Object.entries(profile.tools_enabled)) {
    const defaultEnabled = defaultProfile.tools_enabled[key]
    if (enabled === defaultEnabled) continue
    notes.push(`${enabled ? 'включён' : 'отключён'}: ${key}`)
  }
  if (profile.effects_rag !== defaultProfile.effects_rag) {
    notes.push(`effects-RAG: ${profile.effects_rag ? 'включён' : 'отключён'}`)
  }
  if (profile.target_solutions !== defaultProfile.target_solutions) {
    notes.push(`число решений: ${profile.target_solutions}`)
  }
  if (profile.psa_fp_validation !== defaultProfile.psa_fp_validation) {
    notes.push(
      `валидация ПСА/ФП: ${profile.psa_fp_validation ? 'включена' : 'отключена'}`,
    )
  }
  return notes
}

export function isNonDefaultProfile(
  profile: AnalysisProfile | undefined,
  defaultProfile: AnalysisProfile,
): boolean {
  if (!profile) return false
  return !profilesEqual(profile, defaultProfile)
}
