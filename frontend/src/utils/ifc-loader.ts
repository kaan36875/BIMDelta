import * as THREE from "three";
import * as WebIFC from "web-ifc";
import type { ChangeType } from "../types/diff";
import { CHANGE_COLORS_HEX } from "./colors";

export interface LoadedModel {
  group: THREE.Group;
  globalIdToMeshes: Map<string, THREE.Mesh[]>;
}

let ifcApi: WebIFC.IfcAPI | null = null;

async function getIfcApi(): Promise<WebIFC.IfcAPI> {
  if (ifcApi) return ifcApi;
  ifcApi = new WebIFC.IfcAPI();
  ifcApi.SetWasmPath("/");
  await ifcApi.Init();
  return ifcApi;
}

export async function loadIfcModel(file: File): Promise<LoadedModel> {
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
      /* skip non-readable entities */
    }
  }

  const group = new THREE.Group();
  const globalIdToMeshes = new Map<string, THREE.Mesh[]>();

  api.StreamAllMeshes(modelID, (flatMesh: WebIFC.FlatMesh) => {
    const expressID = flatMesh.expressID;
    const globalId = expressToGlobalId.get(expressID);
    if (!globalId) return;

    const meshes: THREE.Mesh[] = [];

    for (let i = 0; i < flatMesh.geometries.size(); i++) {
      const pg = flatMesh.geometries.get(i);
      const mesh = buildThreeMesh(api, modelID, pg);
      mesh.userData.globalId = globalId;
      mesh.userData.expressID = expressID;
      group.add(mesh);
      meshes.push(mesh);
    }

    globalIdToMeshes.set(globalId, meshes);
  });

  api.CloseModel(modelID);
  return { group, globalIdToMeshes };
}

function buildThreeMesh(
  api: WebIFC.IfcAPI,
  modelID: number,
  pg: WebIFC.PlacedGeometry,
): THREE.Mesh {
  const geom = api.GetGeometry(modelID, pg.geometryExpressID);

  const vertexData = api.GetVertexArray(
    geom.GetVertexData(),
    geom.GetVertexDataSize(),
  );
  const indexData = api.GetIndexArray(
    geom.GetIndexData(),
    geom.GetIndexDataSize(),
  );

  const bufferGeom = new THREE.BufferGeometry();
  const vertCount = vertexData.length / 6;
  const positions = new Float32Array(vertCount * 3);
  const normals = new Float32Array(vertCount * 3);

  for (let j = 0; j < vertCount; j++) {
    positions[j * 3] = vertexData[j * 6];
    positions[j * 3 + 1] = vertexData[j * 6 + 1];
    positions[j * 3 + 2] = vertexData[j * 6 + 2];
    normals[j * 3] = vertexData[j * 6 + 3];
    normals[j * 3 + 1] = vertexData[j * 6 + 4];
    normals[j * 3 + 2] = vertexData[j * 6 + 5];
  }

  bufferGeom.setAttribute(
    "position",
    new THREE.BufferAttribute(positions, 3),
  );
  bufferGeom.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
  bufferGeom.setIndex(
    new THREE.BufferAttribute(new Uint32Array(indexData), 1),
  );

  const matrix = new THREE.Matrix4().fromArray(pg.flatTransformation);
  bufferGeom.applyMatrix4(matrix);

  const material = new THREE.MeshPhongMaterial({
    color: 0xd1d5db,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(bufferGeom, material);
  geom.delete?.();
  return mesh;
}

export function colorizeModel(
  model: LoadedModel,
  changeMap: Map<string, ChangeType>,
  isGhost = false,
): void {
  for (const [globalId, meshes] of model.globalIdToMeshes) {
    const changeType = changeMap.get(globalId);

    for (const mesh of meshes) {
      const mat = mesh.material as THREE.MeshPhongMaterial;

      if (isGhost && changeType === "removed") {
        mat.color.setHex(CHANGE_COLORS_HEX.removed);
        mat.transparent = true;
        mat.opacity = 0.35;
        mat.depthWrite = false;
        mesh.visible = true;
      } else if (isGhost) {
        mesh.visible = false;
      } else if (changeType) {
        mat.color.setHex(CHANGE_COLORS_HEX[changeType]);
        mat.transparent = changeType === "unchanged";
        mat.opacity = changeType === "unchanged" ? 0.3 : 1.0;
        mat.depthWrite = changeType !== "unchanged";
      }
    }
  }
}

export function highlightElement(
  model: LoadedModel,
  globalId: string | null,
  previousId: string | null,
  changeMap: Map<string, ChangeType>,
): void {
  if (previousId) {
    const prevMeshes = model.globalIdToMeshes.get(previousId);
    if (prevMeshes) {
      const ct = changeMap.get(previousId) ?? "unchanged";
      for (const mesh of prevMeshes) {
        const mat = mesh.material as THREE.MeshPhongMaterial;
        mat.color.setHex(CHANGE_COLORS_HEX[ct]);
        mat.emissive.setHex(0x000000);
      }
    }
  }

  if (globalId) {
    const meshes = model.globalIdToMeshes.get(globalId);
    if (meshes) {
      for (const mesh of meshes) {
        const mat = mesh.material as THREE.MeshPhongMaterial;
        mat.emissive.setHex(0x444444);
      }
    }
  }
}

export function zoomToElement(
  model: LoadedModel,
  globalId: string,
  camera: THREE.PerspectiveCamera,
  controls: { target: THREE.Vector3; update: () => void },
): void {
  const meshes = model.globalIdToMeshes.get(globalId);
  if (!meshes?.length) return;

  const box = new THREE.Box3();
  for (const mesh of meshes) {
    box.expandByObject(mesh);
  }

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
