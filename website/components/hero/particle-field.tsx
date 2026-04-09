"use client";

/**
 * ParticleField — R3F particle constellation background for the hero section.
 * Indigo-tinted nodes with animated connection lines representing agent topology.
 * GPU-friendly: uses instanced points + additive blending.
 */

import { useRef, useMemo, useCallback, useState, useEffect } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { PointMaterial, AdaptiveDpr } from "@react-three/drei";
import * as THREE from "three";

/* ── Constants ──────────────────────────────────────────── */
const PARTICLE_COUNT = 1800;
const CONNECTION_DISTANCE = 2.8;
const FIELD_SIZE = 16;
const MAX_CONNECTIONS = 150;

/* ── Particles ──────────────────────────────────────────── */
function Particles({ isDark }: { isDark: boolean }) {
  const pointsRef = useRef<THREE.Points>(null!);
  const linesRef = useRef<THREE.LineSegments>(null!);

  // Generate random particle positions in a sphere
  const { positions, velocities } = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3);
    const vel = new Float32Array(PARTICLE_COUNT * 3);
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      // Distribute in a sphere for organic feel
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = Math.cbrt(Math.random()) * FIELD_SIZE * 0.5;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
      // Slow drift velocities
      vel[i * 3] = (Math.random() - 0.5) * 0.003;
      vel[i * 3 + 1] = (Math.random() - 0.5) * 0.003;
      vel[i * 3 + 2] = (Math.random() - 0.5) * 0.003;
    }
    return { positions: pos, velocities: vel };
  }, []);

  // Pre-allocate connection line buffer
  const linePositions = useMemo(
    () => new Float32Array(MAX_CONNECTIONS * 6),
    []
  );
  const lineColors = useMemo(
    () => new Float32Array(MAX_CONNECTIONS * 6),
    []
  );

  const lineGeom = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(linePositions, 3));
    geom.setAttribute("color", new THREE.BufferAttribute(lineColors, 3));
    geom.setDrawRange(0, 0);
    return geom;
  }, [linePositions, lineColors]);

  // Mouse tracking for subtle interaction
  const mouse = useRef({ x: 0, y: 0 });
  const { viewport } = useThree();

  const onPointerMove = useCallback(
    (e: { clientX: number; clientY: number }) => {
      mouse.current.x =
        ((e.clientX / window.innerWidth) * 2 - 1) * viewport.width * 0.3;
      mouse.current.y =
        (-(e.clientY / window.innerHeight) * 2 + 1) * viewport.height * 0.3;
    },
    [viewport]
  );

  // Animation loop
  useFrame((state) => {
    if (!pointsRef.current) return;
    const posAttr = pointsRef.current.geometry.attributes
      .position as THREE.BufferAttribute;
    const arr = posAttr.array as Float32Array;
    const time = state.clock.elapsedTime;

    // Drift particles
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3;
      arr[i3] += velocities[i3] + Math.sin(time * 0.1 + i) * 0.0005;
      arr[i3 + 1] += velocities[i3 + 1] + Math.cos(time * 0.15 + i) * 0.0005;
      arr[i3 + 2] += velocities[i3 + 2];

      // Soft boundary — wrap particles
      for (let j = 0; j < 3; j++) {
        if (Math.abs(arr[i3 + j]) > FIELD_SIZE * 0.5) {
          velocities[i3 + j] *= -1;
        }
      }
    }
    posAttr.needsUpdate = true;

    // Subtle camera drift following mouse
    state.camera.position.x +=
      (mouse.current.x * 0.3 - state.camera.position.x) * 0.02;
    state.camera.position.y +=
      (mouse.current.y * 0.3 - state.camera.position.y) * 0.02;
    state.camera.lookAt(0, 0, 0);

    // Calculate connections (nearest neighbors)
    let lineIdx = 0;
    const indigo = { r: 0.39, g: 0.4, b: 0.95 }; // #6366F1

    for (let i = 0; i < PARTICLE_COUNT && lineIdx < MAX_CONNECTIONS; i += 2) {
      const i3 = i * 3;
      for (
        let j = i + 1;
        j < Math.min(i + 50, PARTICLE_COUNT) && lineIdx < MAX_CONNECTIONS;
        j++
      ) {
        const j3 = j * 3;
        const dx = arr[i3] - arr[j3];
        const dy = arr[i3 + 1] - arr[j3 + 1];
        const dz = arr[i3 + 2] - arr[j3 + 2];
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

        if (dist < CONNECTION_DISTANCE) {
          const alpha = 1 - dist / CONNECTION_DISTANCE;
          const idx = lineIdx * 6;
          linePositions[idx] = arr[i3];
          linePositions[idx + 1] = arr[i3 + 1];
          linePositions[idx + 2] = arr[i3 + 2];
          linePositions[idx + 3] = arr[j3];
          linePositions[idx + 4] = arr[j3 + 1];
          linePositions[idx + 5] = arr[j3 + 2];

          lineColors[idx] = indigo.r * alpha;
          lineColors[idx + 1] = indigo.g * alpha;
          lineColors[idx + 2] = indigo.b * alpha;
          lineColors[idx + 3] = indigo.r * alpha * 0.5;
          lineColors[idx + 4] = indigo.g * alpha * 0.5;
          lineColors[idx + 5] = indigo.b * alpha * 0.5;
          lineIdx++;
        }
      }
    }

    lineGeom.setDrawRange(0, lineIdx * 2);
    (
      lineGeom.attributes.position as THREE.BufferAttribute
    ).needsUpdate = true;
    (lineGeom.attributes.color as THREE.BufferAttribute).needsUpdate = true;

    // Slow global rotation
    pointsRef.current.rotation.y = time * 0.015;
    if (linesRef.current) {
      linesRef.current.rotation.y = time * 0.015;
    }
  });

  return (
    <group>
      <points ref={pointsRef}>
        <bufferGeometry>
          {/* @ts-expect-error R3F bufferAttribute typing mismatch with newer Three.js */}
          <bufferAttribute
            attach="attributes-position"
            count={PARTICLE_COUNT}
            array={positions}
            itemSize={3}
          />
        </bufferGeometry>
        <PointMaterial
          transparent
          color={isDark ? "#6366F1" : "#4F46E5"}
          size={0.06}
          sizeAttenuation
          depthWrite={false}
          blending={isDark ? THREE.AdditiveBlending : THREE.NormalBlending}
          opacity={isDark ? 1 : 0.6}
        />
      </points>
      <lineSegments ref={linesRef} geometry={lineGeom}>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={isDark ? 0.5 : 0.25}
          blending={isDark ? THREE.AdditiveBlending : THREE.NormalBlending}
          depthWrite={false}
        />
      </lineSegments>
    </group>
  );
}

/* ── Accent glow orbs ───────────────────────────────────── */
function GlowOrbs({ isDark }: { isDark: boolean }) {
  const ref = useRef<THREE.Group>(null!);

  useFrame((state) => {
    if (!ref.current) return;
    const t = state.clock.elapsedTime;
    ref.current.children.forEach((child, i) => {
      child.position.x = Math.sin(t * 0.2 + i * 2.1) * 4;
      child.position.y = Math.cos(t * 0.15 + i * 1.7) * 3;
      child.position.z = Math.sin(t * 0.1 + i * 3.3) * 2;
    });
  });

  return (
    <group ref={ref}>
      {[0.9, 0.6, 0.5].map((scale, i) => (
        <mesh key={i} scale={scale}>
          <sphereGeometry args={[1, 16, 16]} />
          <meshBasicMaterial
            color={i === 0 ? "#6366F1" : i === 1 ? "#A78BFA" : "#818CF8"}
            transparent
            opacity={isDark ? 0.09 : 0.04}
            blending={isDark ? THREE.AdditiveBlending : THREE.NormalBlending}
          />
        </mesh>
      ))}
    </group>
  );
}

/* ── Exported Canvas wrapper ────────────────────────────── */
export default function ParticleField() {
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  return (
    <Canvas
      camera={{ position: [0, 0, 10], fov: 50 }}
      dpr={[1, 1.5]}
      gl={{ antialias: false, alpha: true, powerPreference: "high-performance" }}
      style={{ background: "transparent" }}
      frameloop="demand"
      onCreated={({ gl, invalidate }) => {
        gl.setAnimationLoop(() => invalidate());
      }}
    >
      <AdaptiveDpr pixelated />
      <Particles isDark={isDark} />
      <GlowOrbs isDark={isDark} />
    </Canvas>
  );
}
