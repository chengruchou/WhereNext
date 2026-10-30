// The app's colors in one place: one accent, neutrals, and the theme surfaces.
// The map draws with these hex values directly, since its pins and lines sit
// outside the Vuetify theme.

export const palette = {
  accent: '#2a62c9',
  accentStrong: '#1d4a9c',
  accentSoft: '#9db9ec',
  neutral: '#5f6670',
  neutralStrong: '#3f454d',
  neutralSoft: '#c5cad1',
}

export const lightColors = {
  'background': '#f5f6f8',
  'surface': '#ffffff',
  'primary': palette.accent,
  'secondary': palette.neutral,
  'on-primary': '#ffffff',
  'on-secondary': '#ffffff',
}

export const darkColors = {
  'background': '#111317',
  'surface': '#181b20',
  'primary': '#8ab4ff',
  'secondary': '#a3aab4',
  'on-primary': '#0b1a33',
  'on-secondary': '#111317',
}
