import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResumeTab } from "@/components/ResumeTab";
import { CompaniesTab } from "@/components/CompaniesTab";
import { RolesTab } from "@/components/RolesTab";
import { Footer } from "@/components/Footer";
import { AboutModal } from "@/components/AboutModal";
import { PreferencesModal } from "@/components/PreferencesModal";

function App() {
  const [showAbout, setShowAbout] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);

  return (
    <div className="min-h-screen relative overflow-hidden" style={{ background: "var(--app-gradient)" }}>
      {/* Aurora background orbs */}
      <div className="pointer-events-none" aria-hidden="true">
        <div className="glass-orb glass-orb-1" />
        <div className="glass-orb glass-orb-2" />
        <div className="glass-orb glass-orb-3" />
      </div>

      {/* Decorative vine — climbs up the right edge on load */}
      {/* eslint-disable-next-line jsx-a11y/alt-text */}
      <img src="/vine.png" alt="" aria-hidden="true" className="vine-overlay" />

      <Tabs defaultValue="resume">
        {/*
          Sticky header — contains both the title block and the full-width tab band.
          Keeping them in one element means the tab band sticks at exactly the right
          offset without any hardcoded pixel arithmetic.
        */}
        <header
          className="sticky top-0 z-20"
          style={{
            background: "var(--glass-header-bg)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
          }}
        >
          {/* Title section */}
          <div
            className="py-7 text-center border-b"
            style={{ borderColor: "var(--glass-border)" }}
          >
            <h1
              className="text-5xl font-black tracking-tight text-white leading-none"
              style={{ fontFamily: "var(--font-display)" }}
            >
              VerdantMe
            </h1>
            <p className="mt-2 text-sm" style={{ color: "rgba(255,255,255,0.50)" }}>
              Discover companies and roles matched to your resume
            </p>
          </div>

          {/* Full-width tab navigation band */}
          <div
            className="border-b"
            style={{ borderColor: "var(--glass-border)" }}
          >
            <TabsList className="justify-center">
              <TabsTrigger value="resume">📄 Upload Resume</TabsTrigger>
              <TabsTrigger value="companies">🏢 Discover Companies</TabsTrigger>
              <TabsTrigger value="roles">💼 Discover Roles</TabsTrigger>
            </TabsList>
          </div>
        </header>

        {/* Page content — add bottom padding for sticky footer */}
        <main className="relative z-10 max-w-6xl mx-auto px-6 py-8 pb-20">
          <TabsContent value="resume">
            <ResumeTab />
          </TabsContent>
          <TabsContent value="companies">
            <CompaniesTab />
          </TabsContent>
          <TabsContent value="roles">
            <RolesTab />
          </TabsContent>
        </main>
      </Tabs>

      {/* Footer with About and Preferences modals */}
      <Footer
        showAbout={showAbout}
        onAboutChange={setShowAbout}
        showPreferences={showPreferences}
        onPreferencesChange={setShowPreferences}
      />
      <AboutModal open={showAbout} onOpenChange={setShowAbout} />
      <PreferencesModal open={showPreferences} onOpenChange={setShowPreferences} />
    </div>
  );
}

export default App;
