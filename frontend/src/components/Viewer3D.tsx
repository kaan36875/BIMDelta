import { useCallback, useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { useDiffStore } from "../store/diff-store";
import type { ChangeType } from "../types/diff";
import {
  type LoadedModel,
  colorizeModel,
  highlightElement,
  loadIfcModel,
  zoomToElement,
} from "../utils/ifc-loader";

export function Viewer3D() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    v2Model: LoadedModel | null;
    v1Model: LoadedModel | null;
    changeMap: Map<string, ChangeType>;
    raycaster: THREE.Raycaster;
    mouse: THREE.Vector2;
  } | null>(null);

  const { diffResult, v1File, v2File, selectedElementId, selectElement } =
    useDiffStore();

  const prevSelectedRef = useRef<string | null>(null); // kept for future use

  const initScene = useCallback(() => {
    const container = containerRef.current;
    if (!container || sceneRef.current) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setClearColor(0xf3f4f6);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      1000,
    );
    camera.position.set(20, 15, 20);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);
    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
    dirLight2.position.set(-10, 10, -10);
    scene.add(dirLight2);

    const gridHelper = new THREE.GridHelper(50, 50, 0xcccccc, 0xe5e5e5);
    scene.add(gridHelper);

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    sceneRef.current = {
      renderer,
      scene,
      camera,
      controls,
      v2Model: null,
      v1Model: null,
      changeMap: new Map(),
      raycaster,
      mouse,
    };

    const animate = () => {
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!container) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener("resize", handleResize);

    const handleClick = (e: MouseEvent) => {
      const s = sceneRef.current;
      if (!s?.v2Model) return;

      const rect = renderer.domElement.getBoundingClientRect();
      s.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      s.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      s.raycaster.setFromCamera(s.mouse, s.camera);

      const meshes: THREE.Mesh[] = [];
      s.v2Model.group.traverse((obj) => {
        if (obj instanceof THREE.Mesh) meshes.push(obj);
      });
      if (s.v1Model) {
        s.v1Model.group.traverse((obj) => {
          if (obj instanceof THREE.Mesh && obj.visible) meshes.push(obj);
        });
      }

      const hits = s.raycaster.intersectObjects(meshes);
      if (hits.length > 0) {
        const globalId = hits[0].object.userData.globalId;
        if (globalId) selectElement(globalId);
      } else {
        selectElement(null);
      }
    };
    renderer.domElement.addEventListener("click", handleClick);

    return () => {
      window.removeEventListener("resize", handleResize);
      renderer.domElement.removeEventListener("click", handleClick);
      renderer.dispose();
      container.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
  }, [selectElement]);

  useEffect(() => {
    const cleanup = initScene();
    return cleanup;
  }, [initScene]);

  useEffect(() => {
    if (!diffResult || !v2File || !sceneRef.current) return;

    const s = sceneRef.current;

    const changeMap = new Map<string, ChangeType>();
    for (const el of diffResult.elements) {
      changeMap.set(el.global_id, el.change_type);
    }
    s.changeMap = changeMap;

    let cancelled = false;

    (async () => {
      if (s.v2Model) {
        s.scene.remove(s.v2Model.group);
        s.v2Model = null;
      }
      if (s.v1Model) {
        s.scene.remove(s.v1Model.group);
        s.v1Model = null;
      }

      const v2Model = await loadIfcModel(v2File);
      if (cancelled) return;
      colorizeModel(v2Model, changeMap);
      s.scene.add(v2Model.group);
      s.v2Model = v2Model;

      fitCameraToModel(v2Model, s.camera, s.controls);

      if (v1File) {
        const v1Model = await loadIfcModel(v1File);
        if (cancelled) return;
        colorizeModel(v1Model, changeMap, true);
        s.scene.add(v1Model.group);
        s.v1Model = v1Model;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [diffResult, v1File, v2File]);

  useEffect(() => {
    const s = sceneRef.current;
    if (!s?.v2Model) return;

    highlightElement(
      s.v2Model,
      s.v1Model,
      s.scene,
      selectedElementId,
      s.changeMap,
    );

    if (selectedElementId) {
      const changeType = s.changeMap.get(selectedElementId);
      if (changeType === "removed" && s.v1Model) {
        zoomToElement(s.v1Model, selectedElementId, s.camera, s.controls);
      } else {
        zoomToElement(s.v2Model, selectedElementId, s.camera, s.controls);
      }
    }

    prevSelectedRef.current = selectedElementId;
  }, [selectedElementId]);

  return (
    <div ref={containerRef} className="w-full h-full min-h-0 bg-gray-100" />
  );
}

function fitCameraToModel(
  model: LoadedModel,
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
) {
  const box = new THREE.Box3().setFromObject(model.group);
  if (box.isEmpty()) return;

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const dist = maxDim * 1.8;

  camera.position.set(
    center.x + dist,
    center.y + dist * 0.6,
    center.z + dist,
  );
  controls.target.copy(center);
  controls.update();
}
