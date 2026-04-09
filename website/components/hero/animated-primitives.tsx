"use client";

/**
 * Shared animated primitives used across all marketing sections.
 * TiltCard, SpotlightCard, AnimatedGridBg, GlowBorder, ScrollReveal, MagneticHover
 */

import { useRef, useState, useEffect, useCallback } from "react";

/* ── TiltCard — 3D perspective tilt on hover ────────────── */
export function TiltCard({
  children,
  className,
  style,
  intensity = 8,
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  intensity?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const handleMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      el.style.transform = `perspective(800px) rotateY(${x * intensity}deg) rotateX(${-y * intensity}deg) scale3d(1.02, 1.02, 1.02)`;
    },
    [intensity]
  );

  const handleLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.transform = "perspective(800px) rotateY(0deg) rotateX(0deg) scale3d(1, 1, 1)";
  }, []);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        ...style,
        transition: "transform 0.4s cubic-bezier(0.03, 0.98, 0.52, 0.99)",
        transformStyle: "preserve-3d",
        willChange: "transform",
      }}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
    >
      {children}
    </div>
  );
}

/* ── SpotlightCard — mouse-following spotlight glow ─────── */
export function SpotlightCard({
  children,
  className,
  style,
  spotlightColor = "rgba(99,102,241,0.08)",
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  spotlightColor?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [hovering, setHovering] = useState(false);

  const handleMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }, []);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        ...style,
        position: "relative",
        overflow: "hidden",
      }}
      onMouseMove={handleMove}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      {/* Spotlight glow */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          pointerEvents: "none",
          background: hovering
            ? `radial-gradient(400px circle at ${pos.x}px ${pos.y}px, ${spotlightColor}, transparent 60%)`
            : "none",
          transition: "opacity 0.3s",
          opacity: hovering ? 1 : 0,
          zIndex: 0,
        }}
      />
      <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </div>
  );
}

/* ── GlowBorder — animated gradient border ──────────────── */
export function GlowBorder({
  children,
  className,
  borderRadius = "12px",
  glowOpacity = 0.4,
  hoverOpacity = 0.65,
}: {
  children: React.ReactNode;
  className?: string;
  borderRadius?: string;
  glowOpacity?: number;
  hoverOpacity?: number;
}) {
  const [hover, setHover] = useState(false);

  return (
    <div
      className={`relative ${className || ""}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div
        className="absolute -inset-[1px]"
        style={{
          borderRadius,
          background: "linear-gradient(135deg, #6366F1, #A78BFA, #4F46E5, #7C3AED)",
          backgroundSize: "300% 300%",
          animation: "gradientShift 6s ease infinite",
          opacity: hover ? hoverOpacity : glowOpacity,
          transition: "opacity 0.3s",
        }}
      />
      <div className="relative" style={{ borderRadius, overflow: "hidden" }}>
        {children}
      </div>
    </div>
  );
}

/* ── AnimatedGridBg — subtle animated dot grid ──────────── */
export function AnimatedGridBg({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    const gap = 40;
    const dotRadius = 0.8;

    const resize = () => {
      canvas.width = canvas.offsetWidth * (window.devicePixelRatio || 1);
      canvas.height = canvas.offsetHeight * (window.devicePixelRatio || 1);
      ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = (time: number) => {
      ctx.clearRect(0, 0, canvas.offsetWidth, canvas.offsetHeight);
      const isDark = document.documentElement.classList.contains("dark");
      const baseAlpha = isDark ? 0.15 : 0.08;

      for (let x = gap; x < canvas.offsetWidth; x += gap) {
        for (let y = gap; y < canvas.offsetHeight; y += gap) {
          const wave = Math.sin(time * 0.001 + x * 0.01 + y * 0.01) * 0.5 + 0.5;
          const alpha = baseAlpha + wave * 0.08;
          ctx.beginPath();
          ctx.arc(x, y, dotRadius, 0, Math.PI * 2);
          ctx.fillStyle = isDark
            ? `rgba(99,102,241,${alpha})`
            : `rgba(79,70,229,${alpha})`;
          ctx.fill();
        }
      }
      animId = requestAnimationFrame(draw);
    };
    animId = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 w-full h-full pointer-events-none ${className || ""}`}
      style={{ opacity: 0.6 }}
      aria-hidden="true"
    />
  );
}

/* ── ScrollReveal — Anime.js scroll-triggered reveal ────── */
export function ScrollReveal({
  children,
  className,
  style,
  delay = 0,
  distance = 30,
  duration = 700,
  direction = "up",
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  delay?: number;
  distance?: number;
  duration?: number;
  direction?: "up" | "down" | "left" | "right";
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const translateProp =
      direction === "left" || direction === "right" ? "translateX" : "translateY";
    const sign = direction === "down" || direction === "right" ? -1 : 1;

    el.style.opacity = "0";
    el.style.transform = `${translateProp}(${sign * distance}px)`;

    let cancelled = false;
    const run = async () => {
      const { animate } = await import("animejs");
      if (cancelled) return;

      const obs = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) {
            animate(el, {
              opacity: [0, 1],
              [translateProp]: [sign * distance, 0],
              duration,
              delay,
              easing: "easeOutCubic",
            });
            obs.disconnect();
          }
        },
        { threshold: 0.1 }
      );
      obs.observe(el);
    };
    run();
    return () => { cancelled = true; };
  }, [delay, distance, duration, direction]);

  return (
    <div ref={ref} className={className} style={style}>
      {children}
    </div>
  );
}

/* ── MagneticHover — element subtly follows cursor ──────── */
export function MagneticHover({
  children,
  className,
  strength = 0.3,
}: {
  children: React.ReactNode;
  className?: string;
  strength?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const handleMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = (e.clientX - cx) * strength;
      const dy = (e.clientY - cy) * strength;
      el.style.transform = `translate(${dx}px, ${dy}px)`;
    },
    [strength]
  );

  const handleLeave = useCallback(() => {
    const el = ref.current;
    if (el) el.style.transform = "translate(0, 0)";
  }, []);

  return (
    <div
      ref={ref}
      className={className}
      style={{ transition: "transform 0.3s cubic-bezier(0.03, 0.98, 0.52, 0.99)" }}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
    >
      {children}
    </div>
  );
}

/* ── Shared keyframes (import this style once in parent) ── */
export function SharedKeyframes() {
  return (
    <style jsx global>{`
      @keyframes gradientShift {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
      }
      @keyframes floatSlow {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(-8px); }
      }
    `}</style>
  );
}
