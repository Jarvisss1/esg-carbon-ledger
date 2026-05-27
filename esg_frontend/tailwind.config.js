/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border, 240 5.9% 90%))",
        input: "hsl(var(--input, 240 5.9% 90%))",
        ring: "hsl(var(--ring, 142.1 76.2% 36.3%))",
        background: "hsl(var(--background, 240 10% 3.9%))",
        foreground: "hsl(var(--foreground, 0 0% 98%))",
        primary: {
          DEFAULT: "hsl(var(--primary, 142.1 76.2% 36.3%))",
          foreground: "hsl(var(--primary-foreground, 355.7 100% 97.3%))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary, 240 3.7% 15.9%))",
          foreground: "hsl(var(--secondary-foreground, 0 0% 98%))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive, 0 84.2% 60.2%))",
          foreground: "hsl(var(--destructive-foreground, 0 0% 98%))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted, 240 3.7% 15.9%))",
          foreground: "hsl(var(--muted-foreground, 240 5% 64.9%))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent, 240 3.7% 15.9%))",
          foreground: "hsl(var(--accent-foreground, 0 0% 98%))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover, 240 10% 3.9%))",
          foreground: "hsl(var(--popover-foreground, 0 0% 98%))",
        },
        card: {
          DEFAULT: "hsl(var(--card, 240 10% 6%))",
          foreground: "hsl(var(--card-foreground, 0 0% 98%))",
        },
        emerald: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
          950: '#022c22',
        }
      },
      borderRadius: {
        lg: "var(--radius, 0.5rem)",
        md: "calc(var(--radius, 0.5rem) - 2px)",
        sm: "calc(var(--radius, 0.5rem) - 4px)",
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fadeIn 0.5s ease-out forwards",
      },
    },
  },
  plugins: [],
}
