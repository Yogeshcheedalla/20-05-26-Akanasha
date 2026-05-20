'use client';

import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

export interface Akansha3DInterfaceProps {
  audioStream: MediaStream;
  currentPhoneme: string;
  currentEmotion: string;
}

type BlendshapeName =
  | 'jawOpen'
  | 'mouthFunnel'
  | 'mouthPucker'
  | 'mouthSmileLeft'
  | 'mouthSmileRight'
  | 'mouthFrown'
  | 'cheekPuff'
  | 'browInnerUp'
  | 'browDownLeft'
  | 'browDownRight'
  | 'eyeBlinkLeft'
  | 'eyeBlinkRight'
  | 'eyeLookOutLeft'
  | 'eyeLookInRight'
  | 'eyeLookUp'
  | 'eyeLookDown';

type BlendshapeState = Record<BlendshapeName, number>;
type TimedPhonemeChunk = {
  phoneme: string;
  startsAt: number;
  endsAt: number;
};

type MorphMesh = THREE.Mesh & {
  morphTargetDictionary: Record<string, number>;
  morphTargetInfluences: number[];
};

const HUMAN_MESH_PATH = '/assets/models/akansha-human.glb';

const BLENDSHAPE_NAMES: BlendshapeName[] = [
  'jawOpen',
  'mouthFunnel',
  'mouthPucker',
  'mouthSmileLeft',
  'mouthSmileRight',
  'mouthFrown',
  'cheekPuff',
  'browInnerUp',
  'browDownLeft',
  'browDownRight',
  'eyeBlinkLeft',
  'eyeBlinkRight',
  'eyeLookOutLeft',
  'eyeLookInRight',
  'eyeLookUp',
  'eyeLookDown',
];

function neutralBlendshapes(): BlendshapeState {
  return {
    jawOpen: 0,
    mouthFunnel: 0,
    mouthPucker: 0,
    mouthSmileLeft: 0,
    mouthSmileRight: 0,
    mouthFrown: 0,
    cheekPuff: 0,
    browInnerUp: 0,
    browDownLeft: 0,
    browDownRight: 0,
    eyeBlinkLeft: 0,
    eyeBlinkRight: 0,
    eyeLookOutLeft: 0,
    eyeLookInRight: 0,
    eyeLookUp: 0,
    eyeLookDown: 0,
  };
}

function clamp01(value: number) {
  return THREE.MathUtils.clamp(value, 0, 1);
}

function isAudioStreamActive(audioStream: MediaStream) {
  try {
    const audioTracks = audioStream?.getAudioTracks?.() ?? [];
    return Boolean(
      audioStream?.active &&
        audioTracks.some((track) => track.enabled && track.readyState === 'live')
    );
  } catch {
    return false;
  }
}

function phonemeBlendshapes(phoneme: string): BlendshapeState {
  const target = neutralBlendshapes();
  const normalized = phoneme.trim().toUpperCase();

  if (!normalized) {
    return target;
  }

  // Dentals and alveolars: English T/D/N, Telugu త/ద/న, Hindi त/द/न.
  if (/^(T|D|N|TH|DH|త|ద|న|తా|దా|నా|त|द|न)$/.test(normalized)) {
    target.jawOpen = 0.15;
    target.mouthFunnel = 0;
    target.mouthPucker = 0.1;
    return target;
  }

  // Bilabials: English P/B/M, Telugu ప/బ/మ, Hindi प/ब/म.
  // Jaw remains closed; the lips close with pucker instead of jaw scaling.
  if (/^(P|B|M|ప|బ|మ|పా|బా|మా|प|ब|म)$/.test(normalized)) {
    target.jawOpen = 0;
    target.mouthPucker = 0.25;
    return target;
  }

  // Open vowels: English A/O, Telugu ఆ/ఓ, Hindi आ/ओ.
  if (/^(A|AA|AH|AO|O|OH|OW|ఆ|ఓ|ఆా|ఓా|आ|ओ)$/.test(normalized)) {
    target.jawOpen = 0.65;
    target.mouthFunnel = 0.4;
    return target;
  }

  // Fricatives and sibilants: English S/Sh, Telugu స/ష, Hindi स/श.
  if (/^(S|SH|Z|ZH|F|V|స|ష|సా|షా|स|श)$/.test(normalized)) {
    target.jawOpen = 0.05;
    target.mouthSmileLeft = 0.15;
    target.mouthSmileRight = 0.15;
    target.mouthFunnel = 0.1;
    return target;
  }

  // Mid vowels and soft consonants get a conservative default so unknown phonemes stay safe.
  if (/^(E|EH|I|IH|L|R|N|M|Y|W|K|G)$/.test(normalized)) {
    target.jawOpen = 0.18;
    target.mouthSmileLeft = 0.04;
    target.mouthSmileRight = 0.04;
  }

  return target;
}

function createAudioClock(audioStream: MediaStream) {
  if (typeof window === 'undefined') return null;

  const audioWindow = window as typeof window & {
    webkitAudioContext?: typeof AudioContext;
  };
  const AudioContextConstructor = audioWindow.AudioContext || audioWindow.webkitAudioContext;
  if (!AudioContextConstructor) return null;

  const context = new AudioContextConstructor();
  const source = context.createMediaStreamSource(audioStream);
  const gain = context.createGain();
  gain.gain.value = 0;
  source.connect(gain);
  gain.connect(context.destination);

  return { context, source, gain };
}

function resolveActivePhoneme(queue: TimedPhonemeChunk[], now: number) {
  while (queue.length && queue[0].endsAt < now) {
    queue.shift();
  }

  return queue.find((chunk) => chunk.startsAt <= now && chunk.endsAt >= now)?.phoneme ?? '';
}

function applyEmotion(target: BlendshapeState, emotion: string) {
  const normalizedEmotion = emotion.trim().toUpperCase();

  if (normalizedEmotion === 'SMILING') {
    target.mouthSmileLeft = clamp01(target.mouthSmileLeft + 0.4);
    target.mouthSmileRight = clamp01(target.mouthSmileRight + 0.4);
    target.cheekPuff = clamp01(target.cheekPuff + 0.1);
    target.browInnerUp = clamp01(target.browInnerUp + 0.15);
  }

  if (normalizedEmotion === 'CONCERNED' || normalizedEmotion === 'THINKING') {
    target.browDownLeft = clamp01(target.browDownLeft + 0.3);
    target.browDownRight = clamp01(target.browDownRight + 0.3);
    target.mouthFrown = normalizedEmotion === 'CONCERNED' ? clamp01(target.mouthFrown + 0.15) : target.mouthFrown;
  }

  return target;
}

function fade(t: number) {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

function hash1D(value: number) {
  return (Math.sin(value * 127.1) * 43758.5453123) % 1;
}

function perlin1D(value: number, seed: number) {
  const x0 = Math.floor(value);
  const x1 = x0 + 1;
  const sx = fade(value - x0);
  const n0 = hash1D(x0 + seed);
  const n1 = hash1D(x1 + seed);
  return THREE.MathUtils.lerp(n0, n1, sx) * 2 - 1;
}

function collectMorphMeshes(root: THREE.Object3D) {
  const meshes: MorphMesh[] = [];

  root.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (
      mesh.isMesh &&
      mesh.morphTargetDictionary &&
      mesh.morphTargetInfluences &&
      Array.isArray(mesh.morphTargetInfluences)
    ) {
      meshes.push(mesh as MorphMesh);
    }
  });

  return meshes;
}

function applyBlendshapesToMesh(meshes: MorphMesh[], blendshapes: BlendshapeState) {
  for (const mesh of meshes) {
    for (const name of BLENDSHAPE_NAMES) {
      const index = mesh.morphTargetDictionary[name];
      if (typeof index === 'number') {
        mesh.morphTargetInfluences[index] = clamp01(blendshapes[name]);
      }
    }
  }
}

function DigitalHumanRig({
  audioStream,
  currentPhoneme,
  currentEmotion,
}: Akansha3DInterfaceProps) {
  const rootRef = useRef<THREE.Group>(null);
  const chestRef = useRef<THREE.Group>(null);
  const neckRef = useRef<THREE.Group>(null);
  const eyeTargetRef = useRef<THREE.Object3D>(null);
  const currentBlendshapesRef = useRef<BlendshapeState>(neutralBlendshapes());
  const morphMeshesRef = useRef<MorphMesh[]>([]);
  const audioClockRef = useRef<ReturnType<typeof createAudioClock>>(null);
  const phonemeQueueRef = useRef<TimedPhonemeChunk[]>([]);
  const lastQueuedPhonemeRef = useRef('');
  const nextSaccadeAtRef = useRef(1.5);
  const nextBlinkAtRef = useRef(3);
  const blinkStartedAtRef = useRef(-1);
  const eyeOffsetRef = useRef(new THREE.Vector3(0, 0, 0));
  const [scene, setScene] = useState<THREE.Group | null>(null);

  useEffect(() => {
    const clock = createAudioClock(audioStream);
    audioClockRef.current = clock;

    return () => {
      try {
        clock?.source.disconnect();
        clock?.gain.disconnect();
        void clock?.context.close();
      } catch {
        // Audio-clock cleanup must never affect the canvas lifecycle.
      }
      audioClockRef.current = null;
      phonemeQueueRef.current = [];
      lastQueuedPhonemeRef.current = '';
    };
  }, [audioStream]);

  useEffect(() => {
    const normalized = currentPhoneme.trim();
    const clock = audioClockRef.current;
    const now = clock?.context.currentTime ?? performance.now() / 1000;

    if (!normalized) {
      lastQueuedPhonemeRef.current = '';
      phonemeQueueRef.current = [];
      return;
    }

    if (normalized === lastQueuedPhonemeRef.current) return;

    lastQueuedPhonemeRef.current = normalized;
    phonemeQueueRef.current.push({
      phoneme: normalized,
      startsAt: now,
      endsAt: now + 0.105,
    });
    phonemeQueueRef.current = phonemeQueueRef.current.slice(-24);
  }, [currentPhoneme]);

  useEffect(() => {
    let cancelled = false;
    const loader = new GLTFLoader();

    loader.load(
      HUMAN_MESH_PATH,
      (gltf) => {
        if (cancelled) return;
        const clonedScene = gltf.scene.clone(true) as THREE.Group;
        clonedScene.traverse((child) => {
          const mesh = child as THREE.Mesh;
          if (mesh.isMesh) {
            mesh.castShadow = true;
            mesh.receiveShadow = true;
          }
        });
        setScene(clonedScene);
      },
      undefined,
      () => {
        if (!cancelled) setScene(null);
      }
    );

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    morphMeshesRef.current = scene ? collectMorphMeshes(scene) : [];
  }, [scene]);

  useFrame(({ clock }, delta) => {
    try {
      const elapsed = clock.getElapsedTime();
      const audioNow = audioClockRef.current?.context.currentTime ?? elapsed;
      const audioActive = isAudioStreamActive(audioStream);
      const activePhoneme = resolveActivePhoneme(phonemeQueueRef.current, audioNow);
      const hasBufferedPhoneme = activePhoneme.length > 0;
      const target = audioActive && hasBufferedPhoneme ? phonemeBlendshapes(activePhoneme) : neutralBlendshapes();
      const emotionTarget = applyEmotion(target, currentEmotion);
      const speaking = audioActive && hasBufferedPhoneme;
      const alpha = THREE.MathUtils.clamp(delta * (speaking ? 14 : 18), 0, 1);

      if (!speaking) {
        // Absolute silence lock: the articulators that caused prior bulging are reset exactly.
        currentBlendshapesRef.current.jawOpen = 0;
        currentBlendshapesRef.current.mouthFunnel = 0;
        currentBlendshapesRef.current.mouthPucker = 0;
      }

      for (const name of BLENDSHAPE_NAMES) {
        if (!speaking && (name === 'jawOpen' || name === 'mouthFunnel' || name === 'mouthPucker')) {
          continue;
        }
        currentBlendshapesRef.current[name] = THREE.MathUtils.lerp(
          currentBlendshapesRef.current[name],
          emotionTarget[name],
          alpha
        );
      }

      const thinking = currentEmotion.trim().toUpperCase() === 'THINKING';
      const concerned = currentEmotion.trim().toUpperCase() === 'CONCERNED';
      const blinkCadence = thinking || concerned ? THREE.MathUtils.randFloat(4.6, 6) : THREE.MathUtils.randFloat(3, 6);
      if (elapsed >= nextBlinkAtRef.current) {
        blinkStartedAtRef.current = elapsed;
        nextBlinkAtRef.current = elapsed + blinkCadence;
      }

      const blinkElapsed = elapsed - blinkStartedAtRef.current;
      const blinkPhase =
        blinkElapsed >= 0 && blinkElapsed <= 0.1
          ? blinkElapsed / 0.1
          : blinkElapsed > 0.1 && blinkElapsed <= 0.25
            ? 1 - (blinkElapsed - 0.1) / 0.15
            : 0;
      currentBlendshapesRef.current.eyeBlinkLeft = THREE.MathUtils.lerp(
        currentBlendshapesRef.current.eyeBlinkLeft,
        blinkPhase,
        THREE.MathUtils.clamp(delta * 24, 0, 1)
      );
      currentBlendshapesRef.current.eyeBlinkRight = currentBlendshapesRef.current.eyeBlinkLeft;

      if (elapsed >= nextSaccadeAtRef.current) {
        eyeOffsetRef.current.set(THREE.MathUtils.randFloat(0.02, 0.05), THREE.MathUtils.randFloat(-0.05, 0.05), 0);
        nextSaccadeAtRef.current = elapsed + THREE.MathUtils.randFloat(1.5, 3.5);
      }

      currentBlendshapesRef.current.eyeLookOutLeft = THREE.MathUtils.lerp(
        currentBlendshapesRef.current.eyeLookOutLeft,
        Math.max(0, eyeOffsetRef.current.x),
        THREE.MathUtils.clamp(delta * 8, 0, 1)
      );
      currentBlendshapesRef.current.eyeLookInRight = THREE.MathUtils.lerp(
        currentBlendshapesRef.current.eyeLookInRight,
        Math.max(0, eyeOffsetRef.current.x),
        THREE.MathUtils.clamp(delta * 8, 0, 1)
      );
      currentBlendshapesRef.current.eyeLookUp = THREE.MathUtils.lerp(
        currentBlendshapesRef.current.eyeLookUp,
        thinking ? 0.05 : Math.max(0, eyeOffsetRef.current.y),
        THREE.MathUtils.clamp(delta * 8, 0, 1)
      );
      currentBlendshapesRef.current.eyeLookDown = THREE.MathUtils.lerp(
        currentBlendshapesRef.current.eyeLookDown,
        Math.max(0, -eyeOffsetRef.current.y),
        THREE.MathUtils.clamp(delta * 8, 0, 1)
      );

      applyBlendshapesToMesh(morphMeshesRef.current, currentBlendshapesRef.current);

      const neckNoise = perlin1D(elapsed * 0.32, 9.17) * 0.025;
      const breath = Math.sin(elapsed * 0.72) * 0.018;
      const thinkingTilt = thinking ? THREE.MathUtils.degToRad(2) : 0;

      if (rootRef.current) {
        rootRef.current.rotation.y = THREE.MathUtils.lerp(
          rootRef.current.rotation.y,
          perlin1D(elapsed * 0.18, 2.91) * 0.045,
          0.035
        );
      }
      if (chestRef.current) {
        chestRef.current.position.y = breath;
        chestRef.current.scale.y = 1 + breath * 0.018;
      }
      if (neckRef.current) {
        neckRef.current.rotation.z = THREE.MathUtils.lerp(
          neckRef.current.rotation.z,
          neckNoise + thinkingTilt + (concerned ? -0.012 : 0),
          0.04
        );
      }
      if (eyeTargetRef.current) {
        eyeTargetRef.current.position.x = THREE.MathUtils.lerp(
          eyeTargetRef.current.position.x,
          eyeOffsetRef.current.x + (thinking ? 0.08 : 0),
          0.06
        );
        eyeTargetRef.current.position.y = THREE.MathUtils.lerp(
          eyeTargetRef.current.position.y,
          eyeOffsetRef.current.y + (thinking ? 0.06 : 0),
          0.06
        );
      }
    } catch {
      currentBlendshapesRef.current = neutralBlendshapes();
      applyBlendshapesToMesh(morphMeshesRef.current, currentBlendshapesRef.current);
    }
  });

  return (
    <group ref={rootRef} position={[0, -0.38, 0]}>
      <group ref={chestRef}>
        <group ref={neckRef}>
          {scene && <primitive object={scene} scale={1.02} position={[0, -0.2, 0]} />}
        </group>
      </group>
      <object3D ref={eyeTargetRef} position={[0, 0.18, 1]} />
    </group>
  );
}

function StudioLightingRig() {
  return (
    <>
      <ambientLight intensity={0.28} />
      <directionalLight
        position={[2.4, 3.1, 3.2]}
        intensity={2.35}
        color="#ffd9c2"
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
      />
      <directionalLight position={[-2.8, 1.4, 2.4]} intensity={0.68} color="#9ec8ff" />
      <spotLight
        position={[0, 2.6, -2.4]}
        angle={0.48}
        penumbra={0.78}
        intensity={1.1}
        color="#d8f3ff"
      />
    </>
  );
}

function SoftDepthBackdrop() {
  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: '#070b18',
        transparent: true,
        opacity: 0.96,
        depthWrite: false,
      }),
    []
  );

  return (
    <group position={[0, 0, -1.35]}>
      <mesh material={material}>
        <planeGeometry args={[5.4, 4.4]} />
      </mesh>
    </group>
  );
}

export function Akansha3DInterface({
  audioStream,
  currentPhoneme,
  currentEmotion,
}: Akansha3DInterfaceProps) {
  return (
    <div className="relative h-full min-h-[520px] w-full overflow-hidden bg-[#050814]">
      <Canvas
        camera={{ position: [0, 0.16, 3.9], fov: 48, near: 0.1, far: 100 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
        shadows
        className="absolute inset-0"
      >
        <color attach="background" args={['#050814']} />
        <fog attach="fog" args={['#050814', 3.9, 7.2]} />
        <StudioLightingRig />
        <SoftDepthBackdrop />
        <Suspense fallback={null}>
          <DigitalHumanRig
            audioStream={audioStream}
            currentPhoneme={currentPhoneme}
            currentEmotion={currentEmotion}
          />
        </Suspense>
      </Canvas>
    </div>
  );
}

export default Akansha3DInterface;
