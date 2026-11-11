"use client";

// Low-poly architectural maquette of a FICTIONAL school, rendered on demand only
// (frameloop="demand"): no continuous animation loop. Colours come exclusively from
// engine outputs passed in via `tints`.

import { Canvas, useThree, type ThreeEvent } from "@react-three/fiber";
import { Edges, OrbitControls } from "@react-three/drei";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { ZONES, visibleOnFloor, type FloorId, type ZoneId } from "@/lib/zones";

export interface SceneHandle { resetView: () => void }

const CAMERA_POS: [number, number, number] = [19, 17, 24];
const TARGET: [number, number, number] = [2.5, 0.6, 1];

function Invalidator({ deps }: { deps: unknown[] }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => { invalidate(); }, [invalidate, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function Trees() {
  const spots: [number, number][] = [[-7, 5], [-5, 6.3], [-2.5, 5.6], [5, 6.2], [7.5, 5.2], [10, 6.3], [11.5, 4.6], [-8, 3.8], [12, 1.8]];
  return (
    <group>
      {spots.map(([x, z], i) => (
        <group key={i} position={[x, 0, z]}>
          <mesh position={[0, 0.25, 0]}><cylinderGeometry args={[0.06, 0.08, 0.5, 6]} /><meshStandardMaterial color="#4a3f33" /></mesh>
          <mesh position={[0, 0.8, 0]}><coneGeometry args={[0.45, 1.0, 7]} /><meshStandardMaterial color="#2f5a3e" flatShading /></mesh>
        </group>
      ))}
    </group>
  );
}

function Zones({ tints, selected, hovered, setHovered, onSelect, floor }: {
  tints: Record<ZoneId, string>; selected: ZoneId | null; hovered: ZoneId | null; setHovered: (z: ZoneId | null) => void;
  onSelect: (z: ZoneId) => void; floor: FloorId | "all";
}) {
  return (
    <group>
      {ZONES.map((z) => z.blocks.map((b, i) => {
        const vis = visibleOnFloor(b, floor);
        if (vis === "hidden") return null;
        const isSel = selected === z.id;
        const isHover = hovered === z.id;
        const flat = b.floor === "outdoor";
        return (
          <mesh
            key={`${z.id}-${i}`}
            position={b.pos}
            onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onSelect(z.id); }}
            onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); setHovered(z.id); document.body.style.cursor = "pointer"; }}
            onPointerOut={() => { setHovered(null); document.body.style.cursor = ""; }}
            userData={{ zone: z.id }}
          >
            <boxGeometry args={b.size} />
            <meshStandardMaterial
              color={tints[z.id]}
              transparent={vis === "dim"}
              opacity={vis === "dim" ? 0.18 : flat ? 0.9 : 0.96}
              emissive={isSel ? "#e0a040" : isHover ? "#3987e5" : "#000000"}
              emissiveIntensity={isSel ? 0.35 : isHover ? 0.2 : 0}
              roughness={0.8}
              metalness={0}
            />
            {!flat && <Edges threshold={15} color={isSel ? "#f0c070" : vis === "dim" ? "#2a3038" : "#0b0e12"} />}
          </mesh>
        );
      }))}
    </group>
  );
}

const SchoolScene = forwardRef<SceneHandle, {
  tints: Record<ZoneId, string>; selected: ZoneId | null; onSelect: (z: ZoneId | null) => void; floor: FloorId | "all"; labels: Record<ZoneId, string>;
}>(function SchoolScene({ tints, selected, onSelect, floor }, ref) {
  const controls = useRef<{ reset: () => void } | null>(null);
  const [hovered, setHovered] = useState<ZoneId | null>(null);
  useImperativeHandle(ref, () => ({ resetView: () => controls.current?.reset() }), []);
  const tintKey = useMemo(() => JSON.stringify(tints), [tints]);

  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      camera={{ position: CAMERA_POS, fov: 38, near: 0.1, far: 200 }}
      gl={{ antialias: true, powerPreference: "low-power", preserveDrawingBuffer: false }}
      onPointerMissed={() => onSelect(null)}
      data-testid="twin-canvas"
    >
      <color attach="background" args={["#0e1217"]} />
      <ambientLight intensity={0.75} />
      <directionalLight position={[10, 18, 8]} intensity={1.1} />
      <directionalLight position={[-12, 8, -10]} intensity={0.3} />
      {/* ground plate */}
      <mesh position={[2, -0.03, 0.8]} receiveShadow>
        <boxGeometry args={[24, 0.06, 15]} />
        <meshStandardMaterial color="#1a2028" roughness={1} />
      </mesh>
      <gridHelper args={[24, 24, "#232a33", "#1c2229"]} position={[2, 0.001, 0.8]} />
      <Zones tints={tints} selected={selected} hovered={hovered} setHovered={setHovered} onSelect={(z) => onSelect(z)} floor={floor} />
      <Trees />
      <OrbitControls ref={controls as never} makeDefault target={TARGET} enableDamping={false} minDistance={8} maxDistance={45} maxPolarAngle={Math.PI / 2.15} />
      <Invalidator deps={[tintKey, selected, floor, hovered]} />
    </Canvas>
  );
});

export default SchoolScene;
