import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResumeTab } from "@/components/ResumeTab";
import { CompaniesTab } from "@/components/CompaniesTab";
import { RolesTab } from "@/components/RolesTab";

function App() {
  return (
    <div className="min-h-screen relative overflow-hidden" style={{ background: "var(--app-gradient)" }}>
      {/* Aurora background orbs */}
      <div className="pointer-events-none" aria-hidden="true">
        <div className="glass-orb glass-orb-1" />
        <div className="glass-orb glass-orb-2" />
        <div className="glass-orb glass-orb-3" />
      </div>

      {/* Frosted glass header */}
      <header
        className="sticky top-0 z-10 border-b px-6 py-4"
        style={{
          background: "var(--glass-header-bg)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderColor: "var(--glass-border)",
        }}
      >
        <div className="max-w-6xl mx-auto">
          <h1 className="text-xl font-bold tracking-tight text-white">JobFinder</h1>
          <p className="text-sm" style={{ color: "rgba(255,255,255,0.55)" }}>
            Discover companies and roles matched to your resume
          </p>
        </div>
      </header>

      <main className="relative z-10 max-w-6xl mx-auto px-6 py-8">
        <Tabs defaultValue="resume">
          <TabsList className="mb-6">
            <TabsTrigger value="resume">📄 Upload Resume</TabsTrigger>
            <TabsTrigger value="companies">🏢 Discover Companies</TabsTrigger>
            <TabsTrigger value="roles">💼 Discover Roles</TabsTrigger>
          </TabsList>

          <TabsContent value="resume">
            <ResumeTab />
          </TabsContent>
          <TabsContent value="companies">
            <CompaniesTab />
          </TabsContent>
          <TabsContent value="roles">
            <RolesTab />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

export default App;
