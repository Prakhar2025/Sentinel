"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DEMO_MODE } from "@/lib/demo";
import { LogoMark, Wordmark } from "@/components/Logo";
import { useApi } from "@/lib/api";

const NAV = [
  { href: "/", label: "Queue" },
  { href: "/playground", label: "Playground" },
  { href: "/metrics", label: "Evaluation" },
  { href: "/replay", label: "Replay" },
];

export function CommandBar() {
  const pathname = usePathname();
  const { base } = useApi();

  return (
    <header className="sticky top-0 z-20 border-b border-hairline bg-ink/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-6 px-6">
        <Link href="/" className="flex items-center gap-3">
          <LogoMark size={26} />
          <Wordmark />
        </Link>

        <nav className="ml-4 flex items-center gap-1">
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`micro rounded-md px-3 py-1.5 transition-colors ${
                  active ? "bg-raised text-text" : "hover:text-text"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <span className="micro hidden md:inline">
            {DEMO_MODE ? "static snapshot" : base.replace(/^https?:\/\//, "")}
          </span>
          <span className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-allow opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-allow" />
            </span>
            <span className="micro text-allow">live</span>
          </span>
        </div>
      </div>
    </header>
  );
}
