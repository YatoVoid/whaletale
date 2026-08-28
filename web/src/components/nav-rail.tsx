"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarRange,
  FileText,
  LayoutList,
  Settings,
  SquareStack,
  Users,
} from "lucide-react";
import { cn } from "@/lib/cn";

const ITEMS = [
  { href: "/", label: "Overview", icon: LayoutList },
  { href: "/schedule", label: "Schedule", icon: CalendarRange },
  { href: "/spaces", label: "Spaces", icon: SquareStack },
  { href: "/occupants", label: "Occupants", icon: Users },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export function NavRail({ siteName }: { siteName: string }) {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Sections"
      className="wt-hairline flex shrink-0 flex-col border-r bg-paper md:w-52"
    >
      <div className="wt-hairline border-b px-4 py-4">
        <div className="font-serif text-base text-ink">WhaleTale</div>
        <div className="mt-0.5 truncate text-xs text-ink-soft">{siteName}</div>
      </div>
      <ul className="flex flex-1 flex-col gap-0.5 p-2">
        {ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-sm",
                  active
                    ? "bg-[color-mix(in_srgb,var(--color-field)_10%,transparent)] text-ink"
                    : "text-ink-soft hover:text-ink",
                )}
              >
                <Icon
                  size={16}
                  strokeWidth={1.5}
                  className={active ? "text-field" : "text-ink-soft"}
                  aria-hidden
                />
                <span className="hidden md:inline">{label}</span>
                <span className="md:hidden sr-only">{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
