import type { Config } from 'tailwindcss';

// ChaiUI on Tailwind 3: the tokens are CSS variables in app/globals.css, mapped to names here.
export default {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-manrope)', 'system-ui', 'sans-serif'],
        montserrat: ['var(--font-montserrat)', 'system-ui', 'sans-serif'],
        brand: ['var(--font-onest)', 'system-ui', 'sans-serif'],
      },
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        primary: { DEFAULT: 'var(--primary)', foreground: 'var(--primary-foreground)' },
        muted: { DEFAULT: 'var(--muted)', foreground: 'var(--muted-foreground)' },
        faint: 'var(--faint)',
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        brand: 'var(--brand)',
        highlight: 'var(--highlight)',
        'card-edge': 'var(--card-edge)',
      },
      borderRadius: { lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)', sm: 'calc(var(--radius) - 4px)' },
      keyframes: { 'chai-spin': { to: { transform: 'translate(-50%, -50%) rotate(360deg)' } } },
      animation: { 'chai-spin': 'chai-spin 4s linear infinite' },
    },
  },
  plugins: [],
} satisfies Config;
