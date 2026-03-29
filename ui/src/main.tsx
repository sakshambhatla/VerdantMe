import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/queryClient'
import { ModeProvider } from '@/contexts/ModeContext'
import { AuthProvider } from '@/components/AuthProvider'
import { RoleProvider } from '@/contexts/RoleContext'
import { LandingPage } from '@/components/LandingPage'
import { AboutPage } from '@/components/AboutPage'
import { PrivacyPolicyPage } from '@/components/PrivacyPolicyPage'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ModeProvider>
        <AuthProvider>
          <QueryClientProvider client={queryClient}>
            <RoleProvider>
              <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="/privacy" element={<PrivacyPolicyPage />} />
                <Route path="/app/*" element={<App />} />
              </Routes>
            </RoleProvider>
          </QueryClientProvider>
        </AuthProvider>
      </ModeProvider>
    </BrowserRouter>
  </StrictMode>,
)
