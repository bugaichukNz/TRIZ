import { useEffect, useMemo, useState } from 'react'
import Alert from '@mui/material/Alert'
import Typography from '@mui/material/Typography'
import { getAuthToken } from '../../app/authToken'
import type { AnalysisProfile, ToolRegistryItem } from '../../types/triz'
import { isNonDefaultProfile } from '../chat/AnalysisProfilePanel'

const baseUrl = import.meta.env.VITE_API_URL ?? ''

interface RegistryResponse {
  tools: ToolRegistryItem[]
  default_profile: AnalysisProfile
}

interface ProfileBadgeProps {
  profile: AnalysisProfile | undefined
}

export function NonStandardProfileBadge({ profile }: ProfileBadgeProps) {
  const [defaultProfile, setDefaultProfile] = useState<AnalysisProfile | null>(null)
  const [toolTitles, setToolTitles] = useState<Record<string, string>>({})

  useEffect(() => {
    const token = getAuthToken()
    void fetch(`${baseUrl}/analysis/profile/registry`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(async (res) => {
        if (!res.ok) return null
        return res.json() as Promise<RegistryResponse>
      })
      .then((data) => {
        if (!data) return
        setDefaultProfile(data.default_profile)
        const titles: Record<string, string> = {}
        for (const tool of data.tools) {
          titles[tool.key] = tool.title
        }
        setToolTitles(titles)
      })
      .catch(() => {})
  }, [])

  const deviations = useMemo(() => {
    if (!profile || !defaultProfile) return []
    if (!isNonDefaultProfile(profile, defaultProfile)) return []

    const notes: string[] = []
    for (const [key, enabled] of Object.entries(profile.tools_enabled)) {
      const defaultEnabled = defaultProfile.tools_enabled[key]
      if (enabled === defaultEnabled) continue
      const title = toolTitles[key] ?? key
      notes.push(`${enabled ? 'включён' : 'отключён'}: ${title}`)
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
  }, [profile, defaultProfile, toolTitles])

  if (deviations.length === 0) return null

  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        Анализ выполнен с нестандартным профилем
      </Typography>
      <Typography variant="body2" component="ul" sx={{ m: 0, pl: 2 }}>
        {deviations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </Typography>
    </Alert>
  )
}
