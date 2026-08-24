/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Полная шкала: пропущенные ступени 200/300/400/800 шаблоны уже
        // использовали (border-brand-300, text-brand-400 и т.д.), но Tailwind
        // молча не выдаёт класс для несуществующего оттенка – рамки и подписи
        // оставались бесцветными. Значения – те же, что у синего у Tailwind,
        // на которых построены остальные ступени.
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        }
      }
    }
  },
  plugins: [],
}
