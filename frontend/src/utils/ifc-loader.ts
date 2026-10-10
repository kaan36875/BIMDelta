import * as THREE from "three";
import * as WebIFC from "web-ifc";
import type { ChangeType } from "../types/diff";
import { CHANGE_COLORS_HEX } from "./colors";

interface VertexRange {
  vStart: number;
  vCount: number;
  iStart: number;
  iCount: number;
}

export interface LoadedModel {
  group: THREE.Group;
  mesh: THREE.Mesh;
  elementRanges: Map<string, VertexRange>;
  elementIndexToGlobalId: string[];
  globalIdToElementIndex: Map<string, number>;
}

let ifcApi: WebIFC.IfcAPI | null = null;

async function getIfcApi(): Promise<WebIFC.IfcAPI> {
  if (ifcApi) return ifcApi;
  ifcApi = new WebIFC.IfcAPI();
  ifcApi.SetWasmPath("/");
  await ifcApi.Init();
  return ifcApi;
}

export async function loadIfcModel(
  file: File,
  includeOnly?: Set<string>,
): Promise<LoadedModel> {
  const api = await getIfcApi();
  const data = new Uint8Array(await file.arrayBuffer());
  const modelID = api.OpenModel(data);

  const expressToGlobalId = new Map<number, string>();
  const allTypes = api.GetLineIDsWithType(modelID, WebIFC.IFCPRODUCT, true);
  for (let i = 0; i < allTypes.size(); i++) {
    const eid = allTypes.get(i);
    try {
      const line = api.GetLine(modelID, eid);
      if (line?.GlobalId?.value) {
        expressToGlobalId.set(eid, line.GlobalId.value);
      }
    } catch {
      /* skip */
    }
  }

  const positions: number[] = [];
  const normals: number[] = [];
  const indices: number[] = [];
  const colors: number[] = [];
  const elementRanges = new Map<string, VertexRange>();
  const elementIndexToGlobalId: string[] = [];
  const globalIdToElementIndex = new Map<string, number>();
  let vertexOffset = 0;

  const pos = new THREE.Vector3();
  const norm = new THREE.Vector3();

  api.StreamAllMeshes(modelID, (flatMesh: WebIFC.FlatMesh) => {
    const globalId = expressToGlobalId.get(flatMesh.expressID);
    if (!globalId) return;
    if (includeOnly && !includeOnly.has(globalId)) return;
    if (elementRanges.has(globalId)) return;

    const vStart = vertexOffset;
    const iStart = indices.length;

    for (let i = 0; i < flatMesh.geometries.size(); i++) {
      const pg = flatMesh.geometries.get(i);
      const geom = api.GetGeometry(modelID, pg.geometryExpressID);
      const vertexData = api.GetVertexArray(
        geom.GetVertexData(),
        geom.GetVertexDataSize(),
      );
      const indexData = api.GetIndexArray(
        geom.GetIndexData(),
        geom.GetIndexDataSize(),
      );

      const matrix = new THREE.Matrix4().fromArray(pg.flatTransformation);
      const normalMatrix = new THREE.Matrix3().getNormalMatrix(matrix);
      const vertCount = vertexData.length / 6;

      for (let j = 0; j < vertCount; j++) {
        pos.set(
          vertexData[j * 6],
          vertexData[j * 6 + 1],
          vertexData[j * 6 + 2],
        );
        pos.applyMatrix4(matrix);
        positions.push(pos.x, pos.y, pos.z);

        norm.set(
          vertexData[j * 6 + 3],
          vertexData[j * 6 + 4],
          vertexData[j * 6 + 5],
        );
        norm.applyMatrix3(normalMatrix).normalize();
        normals.push(norm.x, norm.y, norm.z);

        colors.push(0.82, 0.84, 0.86);
      }

      for (let j = 0; j < indexData.length; j++) {
        indices.push(indexData[j] + vertexOffset);
      }

      vertexOffset += vertCount;
      geom.delete?.();
    }

    const vCount = vertexOffset - vStart;
    const iCount = indices.length - iStart;

    if (vCount > 0) {
      globalIdToElementIndex.set(globalId, elementIndexToGlobalId.length);
      elementIndexToGlobalId.push(globalId);
      elementRanges.set(globalId, { vStart, vCount, iStart, iCount });
    }
  });

  api.CloseModel(modelID);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  );
  geometry.setAttribute(
    "normal",
    new THREE.Float32BufferAttribute(normals, 3),
  );
  geometry.setAttribute(
    "color",
    new THREE.Float32BufferAttribute(colors, 3),
  );
  geometry.setIndex(
    new THREE.BufferAttribute(new Uint32Array(indices), 1),
  );

  // Per-vertex element index for raycasting
  const elementIdData = new Float32Array(vertexOffset);
  for (const [gid, range] of elementRanges) {
    const idx = globalIdToElementIndex.get(gid)!;
    for (let i = range.vStart; i < range.vStart + range.vCount; i++) {
      elementIdData[i] = idx;
    }
  }
  geometry.setAttribute(
    "elementId",
    new THREE.Float32BufferAttribute(elementIdData, 1),
  );

  const material = new THREE.MeshPhongMaterial({
    vertexColors: true,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geometry, material);
  const group = new THREE.Group();
  group.add(mesh);

  return {
    group,
    mesh,
    elementRanges,
    elementIndexToGlobalId,
    globalIdToElementIndex,
  };
}

function hexToRgb(hex: number): [number, number, number] {
  return [
    ((hex >> 16) & 0xff) / 255,
    ((hex >> 8) & 0xff) / 255,
    (hex & 0xff) / 255,
  ];
}

export function colorizeModel(
  model: LoadedModel,
  changeMap: Map<string, ChangeType>,
  isGhost = false,
): void {
  const colorAttr = model.mesh.geometry.getAttribute(
    "color",
  ) as THREE.BufferAttribute;
  const arr = colorAttr.array as Float32Array;
  const mat = model.mesh.material as THREE.MeshPhongMaterial;

  mat.wireframe = false;

  if (isGhost) {
    mat.transparent = true;
    mat.opacity = 0.35;
    mat.depthWrite = false;
    const [r, g, b] = hexToRgb(CHANGE_COLORS_HEX.removed);
    for (let i = 0; i < arr.length; i += 3) {
      arr[i] = r;
      arr[i + 1] = g;
      arr[i + 2] = b;
    }
  } else {
    mat.transparent = false;
    mat.opacity = 1.0;
    mat.depthWrite = true;

    for (const [globalId, range] of model.elementRanges) {
      const ct = changeMap.get(globalId) ?? "unchanged";
      const [r, g, b] = hexToRgb(CHANGE_COLORS_HEX[ct]);
      for (let i = range.vStart; i < range.vStart + range.vCount; i++) {
        arr[i * 3] = r;
        arr[i * 3 + 1] = g;
        arr[i * 3 + 2] = b;
      }
    }
  }

  colorAttr.needsUpdate = true;
}

const ISOLATION_COLORS: Record<string, number> = {
  added: 0x22c55e,
  modified: 0xf59e0b,
  removed: 0xef4444,
  unchanged: 0x555555,
};

let activeHighlightObjects: THREE.Object3D[] = [];

export function highlightElement(
  v2Model: LoadedModel,
  v1Model: LoadedModel | null,
  scene: THREE.Scene,
  globalId: string | null,
  changeMap: Map<string, ChangeType>,
): void {
  for (const obj of activeHighlightObjects) {
    scene.remove(obj);
    if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
      obj.geometry.dispose();
      (obj.material as THREE.Material).dispose();
    }
  }
  activeHighlightObjects = [];

  colorizeModel(v2Model, changeMap, false);
  if (v1Model) colorizeModel(v1Model, changeMap, true);

  if (!globalId) return;

  const changeType = changeMap.get(globalId);
  const isRemoved = changeType === "removed";
  const targetModel = isRemoved ? v1Model : v2Model;
  if (!targetModel) return;

  dimModel(v2Model);
  if (v1Model) dimModel(v1Model);

  const range = targetModel.elementRanges.get(globalId);
  if (!range) return;

  // Extract element geometry into a standalone mesh
  const srcGeom = targetModel.mesh.geometry;
  const srcPos = srcGeom.getAttribute("position").array as Float32Array;
  const srcNorm = srcGeom.getAttribute("normal").array as Float32Array;
  const srcIndex = srcGeom.getIndex()!.array;

  const newPos = new Float32Array(range.vCount * 3);
  const newNorm = new Float32Array(range.vCount * 3);
  newPos.set(
    srcPos.subarray(range.vStart * 3, (range.vStart + range.vCount) * 3),
  );
  newNorm.set(
    srcNorm.subarray(range.vStart * 3, (range.vStart + range.vCount) * 3),
  );

  const newIndices = new Uint32Array(range.iCount);
  for (let i = 0; i < range.iCount; i++) {
    newIndices[i] = srcIndex[range.iStart + i] - range.vStart;
  }

  const highlightGeom = new THREE.BufferGeometry();
  highlightGeom.setAttribute(
    "position",
    new THREE.BufferAttribute(newPos, 3),
  );
  highlightGeom.setAttribute(
    "normal",
    new THREE.BufferAttribute(newNorm, 3),
  );
  highlightGeom.setIndex(new THREE.BufferAttribute(newIndices, 1));

  const fillColor = ISOLATION_COLORS[changeType ?? "unchanged"];
  const highlightMesh = new THREE.Mesh(
    highlightGeom,
    new THREE.MeshPhongMaterial({ color: fillColor, side: THREE.DoubleSide }),
  );
  scene.add(highlightMesh);
  activeHighlightObjects.push(highlightMesh);

  const edges = new THREE.EdgesGeometry(highlightGeom, 25);
  const edgeLines = new THREE.LineSegments(
    edges,
    new THREE.LineBasicMaterial({ color: 0x000000 }),
  );
  scene.add(edgeLines);
  activeHighlightObjects.push(edgeLines);
}

function dimModel(model: LoadedModel): void {
  const mat = model.mesh.material as THREE.MeshPhongMaterial;
  mat.wireframe = true;
  mat.transparent = true;
  mat.opacity = 0.2;
  mat.depthWrite = false;

  const colorAttr = model.mesh.geometry.getAttribute(
    "color",
  ) as THREE.BufferAttribute;
  const arr = colorAttr.array as Float32Array;
  for (let i = 0; i < arr.length; i += 3) {
    arr[i] = 0.13;
    arr[i + 1] = 0.13;
    arr[i + 2] = 0.13;
  }
  colorAttr.needsUpdate = true;
}

export function zoomToElement(
  model: LoadedModel,
  globalId: string,
  camera: THREE.PerspectiveCamera,
  controls: { target: THREE.Vector3; update: () => void },
): void {
  const range = model.elementRanges.get(globalId);
  if (!range) return;

  const positions = model.mesh.geometry.getAttribute("position")
    .array as Float32Array;
  const box = new THREE.Box3();
  const v = new THREE.Vector3();

  for (let i = range.vStart; i < range.vStart + range.vCount; i++) {
    v.set(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]);
    box.expandByPoint(v);
  }

  if (box.isEmpty()) return;

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const distance = maxDim * 2.5;

  camera.position.copy(
    center.clone().add(new THREE.Vector3(distance, distance * 0.5, distance)),
  );
  controls.target.copy(center);
  controls.update();
}

export function getClickedGlobalId(
  model: LoadedModel,
  faceIndex: number,
): string | null {
  const index = model.mesh.geometry.getIndex();
  const elementIdAttr = model.mesh.geometry.getAttribute("elementId");
  if (!index || !elementIdAttr) return null;

  const vertexIndex = index.getX(faceIndex * 3);
  const elementIdx = Math.round(elementIdAttr.getX(vertexIndex));
  return model.elementIndexToGlobalId[elementIdx] ?? null;
}
