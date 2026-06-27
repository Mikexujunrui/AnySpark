import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { ThemeProvider } from './hooks/useTheme.js'
import Bookshelf from './components/Bookshelf'
import BookDetail from './components/BookDetail'
import Toast from './components/ui/Toast'
import ErrorBoundary from './components/ui/ErrorBoundary'

export default function App() {
  const location = useLocation()

  return (
    <ThemeProvider>
      <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
          >
            <Routes location={location}>
              <Route path="/" element={<Bookshelf />} />
              <Route path="/book/:bookId" element={<ErrorBoundary><BookDetail /></ErrorBoundary>} />
            </Routes>
          </motion.div>
        </AnimatePresence>
        <Toast />
      </div>
    </ThemeProvider>
  )
}
