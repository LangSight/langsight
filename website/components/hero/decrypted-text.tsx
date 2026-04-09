"use client";

/**
 * DecryptedText — Matrix-style text decode effect.
 * Characters scramble through random glyphs before settling on the real text.
 * Lightweight: pure React + requestAnimationFrame, no external deps.
 */

import { useEffect, useRef, useState } from "react";

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*";

interface DecryptedTextProps {
  text: string;
  /** ms per character reveal (default: 40) */
  speed?: number;
  /** ms before animation starts (default: 0) */
  delay?: number;
  /** CSS class for the wrapper span */
  className?: string;
  /** Inline style */
  style?: React.CSSProperties;
  /** Whether to trigger the animation (default: true) */
  animate?: boolean;
}

export default function DecryptedText({
  text,
  speed = 40,
  delay = 0,
  className,
  style,
  animate = true,
}: DecryptedTextProps) {
  const [display, setDisplay] = useState(text);
  const [started, setStarted] = useState(false);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!animate) {
      setDisplay(text);
      return;
    }

    const timeout = setTimeout(() => {
      setStarted(true);
      let revealed = 0;
      const chars = text.split("");
      const totalChars = chars.length;
      let frame = 0;

      const step = () => {
        frame++;
        // Reveal one character every `speed / 16` frames (~60fps)
        const revealFrame = Math.floor(speed / 16);
        if (frame % revealFrame === 0 && revealed < totalChars) {
          revealed++;
        }

        const result = chars.map((char, i) => {
          if (i < revealed) return char;
          if (char === " ") return " ";
          return GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
        });

        setDisplay(result.join(""));

        if (revealed < totalChars) {
          rafRef.current = requestAnimationFrame(step);
        }
      };

      rafRef.current = requestAnimationFrame(step);
    }, delay);

    return () => {
      clearTimeout(timeout);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [text, speed, delay, animate]);

  return (
    <span
      className={className}
      style={{
        ...style,
        fontFamily: started && display !== text ? "var(--font-geist-mono)" : undefined,
        transition: "font-family 0.3s ease",
      }}
    >
      {display}
    </span>
  );
}
