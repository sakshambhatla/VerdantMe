import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ResumeTab } from "@/components/ResumeTab";
import { CompaniesTab } from "@/components/CompaniesTab";
import { RolesTab } from "@/components/RolesTab";
import { PipelinePage } from "@/components/PipelinePage";
import { OffersPage } from "@/components/OffersPage";
import { DebugLogPanel } from "@/components/DebugLogPanel";
import { TopNav } from "@/components/TopNav";
import { SideNav } from "@/components/SideNav";
import { MobileNav } from "@/components/MobileNav";
import { useAuth } from "@/components/AuthProvider";
import { LoginPage } from "@/components/LoginPage";
import { ModeSelectionPage } from "@/components/ModeSelectionPage";
import { useMode } from "@/contexts/ModeContext";
import { useRole } from "@/contexts/RoleContext";
import { supabase } from "@/lib/supabase";

function App() {
  const { mode } = useMode();
  const { user, loading: authLoading } = useAuth();
  const { isAtLeast } = useRole();
  const [activeTab, setActiveTab] = useState("resume");
  const location = useLocation();
  const navigate = useNavigate();
  const showPipeline = location.pathname.startsWith("/app/pipeline");
  const showOffers = location.pathname === "/app/pipeline/offers";

  // ── Conditional renders ─────────────────────────────────────────────────────

  if (mode === null) {
    return <ModeSelectionPage />;
  }

  if (mode === "managed" && supabase && authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0e0e0e]">
        <span className="h-10 w-10 animate-spin rounded-full border-4 border-[#a3a6ff] border-t-transparent" />
      </div>
    );
  }
  if (mode === "managed" && supabase && !user) {
    return <LoginPage />;
  }

  // ── Determine which content to show ─────────────────────────────────────────

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    if (showPipeline) navigate("/app");
  };

  const handleSideNavClick = (id: string) => {
    if (id === "pipeline") navigate("/app/pipeline");
    else if (id === "offers") navigate("/app/pipeline/offers");
  };

  const sideNavActiveItem = showOffers ? "offers" : "pipeline";

  const renderContent = () => {
    if (showOffers) return <OffersPage />;
    if (showPipeline) return <PipelinePage />;

    switch (activeTab) {
      case "resume":
        return <ResumeTab />;
      case "companies":
        return <CompaniesTab />;
      case "roles":
        return <RolesTab />;
      case "dashboard":
        return (
          <div className="text-center py-20">
            <h2 className="text-2xl font-bold">Dashboard</h2>
            <p className="mt-4 text-[#adaaaa]">Coming soon...</p>
          </div>
        );
      default:
        return <ResumeTab />;
    }
  };

  return (
    <div className="app-shell min-h-screen">
      <TopNav activeTab={activeTab} onTabChange={handleTabChange} />
      <SideNav activeItem={sideNavActiveItem} onItemClick={handleSideNavClick} />

      <main className="ml-0 md:ml-64 pt-24 pb-20 px-8 min-h-screen relative overflow-hidden">
        <div className="asymmetric-glow" />
        <div className="max-w-6xl mx-auto space-y-16">
          {renderContent()}
          {!showPipeline && (mode === "local" || isAtLeast("devtest")) && <DebugLogPanel />}
        </div>
      </main>

      <MobileNav activeTab={showPipeline ? "pipeline" : activeTab} onTabChange={handleTabChange} />
    </div>
  );
}

export default App;
