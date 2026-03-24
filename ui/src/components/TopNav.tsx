import { useLocation, useNavigate } from "react-router-dom";
import { ProfileMenu } from "@/components/ProfileMenu";

interface TopNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const navItems = [
  { label: "Dashboard", tab: "dashboard", path: "/app" },
  { label: "Craft Resume", tab: "resume", path: "/app" },
  { label: "Discover Companies", tab: "companies", path: "/app" },
  { label: "Discover Roles", tab: "roles", path: "/app" },
  { label: "Pipeline", tab: "pipeline", path: "/app/pipeline" },
];

export function TopNav({ activeTab, onTabChange }: TopNavProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const onPipeline = location.pathname === "/app/pipeline";

  const isActive = (item: (typeof navItems)[number]) => {
    if (item.tab === "pipeline") return onPipeline;
    if (onPipeline) return false;
    return activeTab === item.tab;
  };

  const handleClick = (item: (typeof navItems)[number]) => {
    if (item.tab === "pipeline") {
      navigate("/app/pipeline");
    } else {
      onTabChange(item.tab);
      if (onPipeline) navigate("/app");
    }
  };

  return (
    <nav className="fixed top-0 left-0 z-50 flex justify-between items-center w-full px-8 h-20 bg-[#0e0e0e]">
      <div className="text-xl font-black tracking-tighter text-[#a3a6ff]">
        Verdant AI
      </div>

      <div className="hidden md:flex items-center gap-8">
        {navItems.map((item) => (
          <button
            key={item.tab}
            type="button"
            onClick={() => handleClick(item)}
            className={`font-['Inter'] font-bold text-lg tracking-tight transition-colors duration-200 cursor-pointer ${
              isActive(item)
                ? "text-[#a3a6ff] border-b-2 border-[#a3a6ff] pb-1"
                : "text-[#adaaaa] hover:text-white border-b-2 border-transparent pb-1"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-6">
        <button className="material-symbols-outlined text-[#adaaaa] hover:text-white transition-colors cursor-pointer">
          notifications
        </button>
        <ProfileMenu />
      </div>
    </nav>
  );
}
