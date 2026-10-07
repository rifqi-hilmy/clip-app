import { useEffect, useState } from 'react'
import Home from './pages/Home'
import ProjectPage from './pages/ProjectPage'
import SettingsPage from './pages/SettingsPage'

/** Tiny hash router: #/ (home), #/project/:id, #/settings */
function useHashRoute() {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const on = () => setHash(location.hash)
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash
}

export default function App() {
  const hash = useHashRoute()
  const m = hash.match(/^#\/project\/(\d+)/)
  const isSettings = hash.startsWith('#/settings')

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <a href="#/" className="text-lg font-bold tracking-tight">
            ✂️ YouTube <span className="text-rose-500">Clipper</span>
          </a>
          <div className="flex items-center gap-4">
            <a href="#/settings" className="text-xs text-zinc-500 hover:text-zinc-300">⚙ Settings</a>
            <span className="text-xs text-zinc-500">local · 9:16 Shorts / TikTok</span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-6">
        {isSettings ? <SettingsPage /> : m ? <ProjectPage key={m[1]} projectId={Number(m[1])} /> : <Home />}
      </main>
    </div>
  )
}
