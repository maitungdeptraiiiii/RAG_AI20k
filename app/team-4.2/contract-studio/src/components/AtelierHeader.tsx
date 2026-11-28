import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";

type WorkspaceTab = "studio" | "dossier";

interface AtelierHeaderProps {
  active: WorkspaceTab;
  subtitle: string;
  onExitDossier?: () => void;
  actions?: ReactNode;
}

const NAV_ITEMS: Array<{
  id: string;
  label: string;
  href: string;
  tab?: WorkspaceTab;
}> = [
  { id: "chat", label: "Hỏi đáp Luật", href: "/" },
  { id: "studio", label: "Contract Studio", href: "/contract-studio/", tab: "studio" },
  { id: "dossier", label: "Hồ sơ đa văn bản", href: "#ho-so", tab: "dossier" },
  { id: "ask", label: "Đồ thị Hợp đồng", href: "/contracts/ask" },
  { id: "review", label: "Kho luật & Duyệt", href: "/review" },
];

/** Unified Luminous Legal Atelier header shared between single-contract and dossier modes. */
export function AtelierHeader({
  active,
  subtitle,
  onExitDossier,
  actions,
}: AtelierHeaderProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-[#E6E2D8] bg-white/90 backdrop-blur-md">
      <div className="max-w-[1520px] mx-auto px-4 lg:px-6 h-16 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          {onExitDossier && (
            <button
              type="button"
              onClick={onExitDossier}
              className="p-2 rounded-xl border border-[#E6E2D8] text-[#475569] hover:text-[#16325C] hover:bg-[#FAF8F5] transition-colors cursor-pointer"
              title="Về soát một hợp đồng"
            >
              <ArrowLeft size={16} />
            </button>
          )}
          <a
            href="/"
            className="flex items-center gap-2.5 min-w-0 group"
            title="Just-ice Legal AI Workspace"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#16325C] to-[#2563EB] text-white flex items-center justify-center shadow-[0_6px_16px_-4px_rgba(22,50,92,0.4)] shrink-0">
              <svg
                className="w-4.5 h-4.5 text-sky-100"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 2.5L20 7V17L12 21.5L4 17V7L12 2.5Z" />
                <path d="M12 12V21.5" />
                <path d="M12 12L20 7" />
                <path d="M12 12L4 7" />
              </svg>
            </div>
            <div className="min-w-0">
              <div className="font-serif text-[18px] font-semibold text-[#16325C] leading-tight truncate group-hover:text-[#2563EB] transition-colors">
                Just-ice · Contract Studio
              </div>
              <p className="text-[11.5px] text-[#64748B] truncate">{subtitle}</p>
            </div>
          </a>
        </div>

        <nav
          aria-label="Điều hướng ứng dụng"
          className="hidden xl:flex items-center gap-1 p-1 rounded-full bg-[#F4F1EA] border border-[#E6E2D8]"
        >
          {NAV_ITEMS.map((item) => {
            const isActive = item.tab === active;
            if (item.tab === "studio" && active === "dossier" && onExitDossier) {
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={onExitDossier}
                  className="px-3.5 py-1.5 rounded-full text-xs font-medium text-[#475569] hover:text-[#16325C] hover:bg-white/70 transition-colors cursor-pointer"
                >
                  {item.label}
                </button>
              );
            }
            return (
              <a
                key={item.id}
                href={item.href}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all whitespace-nowrap ${
                  isActive
                    ? "bg-[#16325C] text-white shadow-sm"
                    : "text-[#475569] hover:text-[#16325C] hover:bg-white/75"
                }`}
              >
                {item.label}
              </a>
            );
          })}
        </nav>

        <div className="flex items-center gap-3 shrink-0">{actions}</div>
      </div>
    </header>
  );
}
