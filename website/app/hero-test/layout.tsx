import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Hero Test — Internal Preview",
  robots: { index: false, follow: false },
};

export default function HeroTestLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
