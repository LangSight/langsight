"use client";

/**
 * StaggeredReveal — Anime.js-powered staggered entrance animation.
 * Children fade + slide up with configurable delay between each.
 */

import { useEffect, useRef } from "react";

interface StaggeredRevealProps {
  children: React.ReactNode;
  /** ms between each child animation (default: 80) */
  staggerDelay?: number;
  /** ms before the first animation starts (default: 0) */
  delay?: number;
  /** Animation duration per element in ms (default: 700) */
  duration?: number;
  /** Slide distance in px (default: 30) */
  distance?: number;
  /** CSS class for the wrapper */
  className?: string;
  /** Inline style for the wrapper */
  style?: React.CSSProperties;
}

export default function StaggeredReveal({
  children,
  staggerDelay = 80,
  delay = 0,
  duration = 700,
  distance = 30,
  className,
  style,
}: StaggeredRevealProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const items = container.querySelectorAll<HTMLElement>("[data-stagger-item]");
    if (items.length === 0) return;

    // Set initial state
    items.forEach((el) => {
      el.style.opacity = "0";
      el.style.transform = `translateY(${distance}px)`;
    });

    // Animate with Anime.js
    let cancelled = false;

    const run = async () => {
      // Dynamic import to keep Anime.js out of the initial bundle
      const { animate, stagger } = await import("animejs");

      if (cancelled) return;

      animate(items, {
        opacity: [0, 1],
        translateY: [distance, 0],
        delay: stagger(staggerDelay, { start: delay }),
        duration,
        easing: "easeOutCubic",
      });
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [staggerDelay, delay, duration, distance]);

  return (
    <div ref={containerRef} className={className} style={style}>
      {children}
    </div>
  );
}
