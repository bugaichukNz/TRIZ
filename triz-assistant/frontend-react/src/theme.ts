import { createTheme, alpha } from '@mui/material/styles'

const accent = '#1F3964'
const border = '#E5E5E5'
const shadow = '0 1px 3px rgba(0, 0, 0, 0.08)'

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: accent,
      dark: '#152a4a',
      light: '#3d5a8a',
      contrastText: '#FFFFFF',
    },
    background: {
      default: '#FAFAFA',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#1A1A1A',
      secondary: '#6B6B6B',
    },
    divider: border,
  },
  typography: {
    fontFamily: '"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: { fontWeight: 600, fontSize: '1.5rem', lineHeight: 1.5 },
    h2: { fontWeight: 600, fontSize: '1.25rem', lineHeight: 1.5 },
    h3: { fontWeight: 600, fontSize: '1.1rem', lineHeight: 1.5 },
    subtitle1: { fontWeight: 600, fontSize: '0.95rem', lineHeight: 1.5 },
    subtitle2: { fontWeight: 500, fontSize: '0.875rem', lineHeight: 1.5 },
    body1: { fontSize: '0.95rem', lineHeight: 1.5 },
    body2: { fontSize: '0.875rem', lineHeight: 1.5 },
    caption: { fontSize: '0.75rem', lineHeight: 1.5 },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: {
          height: '100%',
        },
        body: {
          height: '100%',
          margin: 0,
          backgroundColor: '#FAFAFA',
          color: '#1A1A1A',
          overflow: 'hidden',
        },
        '#root': {
          height: '100%',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
        rounded: {
          boxShadow: shadow,
          border: `1px solid ${border}`,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: shadow,
          border: `1px solid ${border}`,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          minHeight: 44,
          textTransform: 'none',
          fontWeight: 500,
          boxShadow: 'none',
          '&:hover': {
            boxShadow: 'none',
          },
        },
        contained: {
          boxShadow: shadow,
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          minWidth: 44,
          minHeight: 44,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 500,
        },
        outlined: {
          borderColor: border,
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            '& fieldset': {
              borderColor: border,
            },
          },
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: `1px solid ${border}`,
          boxShadow: 'none',
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          minHeight: 44,
        },
      },
    },
    MuiStepper: {
      styleOverrides: {
        root: {
          padding: 0,
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          border: `1px solid ${border}`,
          boxShadow: shadow,
        },
      },
    },
  },
})

export const chatColors = {
  analystBubble: '#F0F0F0',
  userBubble: alpha(accent, 0.1),
  userBubbleBorder: alpha(accent, 0.2),
  accent,
}
