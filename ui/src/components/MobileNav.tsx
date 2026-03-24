import { useNavigate } from "react-router-dom";

interface MobileNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const items = [
  { label: "Home", icon: "dashboard", tab: "dashboard" },
  { label: "Craft", icon: "description", tab: "resume" },
  { label: "Companies", icon: "apartment", tab: "companies" },
  { label: "Roles", icon: "explore", tab: "roles" },
  { label: "Pipeline", icon: "dynamic_feed", tab: "pipeline" },
];

export function MobileNav({ activeTab, onTabChange }: MobileNavProps) {
  const navigate = useNavigate();

  const handleClick = (tab: string) => {
    if (tab === "pipeline") {
      navigate("/app/pipeline");
    } else {
      onTabChange(tab);
      navigate("/app");
    }
  };

  return (
    <nav className="md:hidden fixed bottom-0 left-0 w-full h-16 bg-[#0e0e0e] flex justify-around items-center z-50 px-4">
      {items.map((item) => (
        <button
          key={item.tab}
          type="button"
          onClick={() => handleClick(item.tab)}
          className={`flex flex-col items-center gap-1 cursor-pointer ${
            activeTab === item.tab ? "text-[#a3a6ff]" : "text-[#adaaaa]"
          }`}
        >
          <span
            className="material-symbols-outlined"
            style={activeTab === item.tab ? { fontVariationSettings: "'FILL' 1" } : undefined}
          >
            {item.icon}
          </span>
          <span className="text-[10px] uppercase font-['Space_Grotesk']">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
