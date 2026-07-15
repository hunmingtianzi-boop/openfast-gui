import * as THREE from './vendor/three.module.min.js';

const math = window.OpenFastHydroGeometryMath;
const COLORS = {
  normal: 0x2c817c,
  potential: 0x7268a6,
  selected: 0xd97732,
  error: 0xb14134,
  joint: 0x365f68,
  orphan: 0x8e9b98,
  water: 0x8cc9d1,
  seabed: 0xb9aa8c,
  division: 0x405c64,
  edge: 0x1d4f4b
};

function disposeObject(object) {
  object.traverse(child => {
    child.geometry?.dispose?.();
    if (Array.isArray(child.material)) child.material.forEach(material => material.dispose?.());
    else child.material?.dispose?.();
  });
}

function clearGroup(group) {
  while (group.children.length) {
    const child = group.children.pop();
    disposeObject(child);
  }
}

function vector3(values) {
  return new THREE.Vector3(values[0], values[1], values[2]);
}

function formatNumber(value, digits = 3) {
  if (!Number.isFinite(Number(value))) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function makeRectangleGeometry(member) {
  const start = vector3(member.start);
  const end = vector3(member.end);
  const sideA = vector3(member.frame.sideA);
  const sideB = vector3(member.frame.sideB);
  const a1 = member.sectionStart?.a;
  const b1 = member.sectionStart?.b;
  const a2 = member.sectionEnd?.a;
  const b2 = member.sectionEnd?.b;
  if (![a1, b1, a2, b2].every(value => Number.isFinite(value) && value > 0)) return null;

  const corners = (center, a, b) => [
    center.clone().addScaledVector(sideA, -a / 2).addScaledVector(sideB, -b / 2),
    center.clone().addScaledVector(sideA, a / 2).addScaledVector(sideB, -b / 2),
    center.clone().addScaledVector(sideA, a / 2).addScaledVector(sideB, b / 2),
    center.clone().addScaledVector(sideA, -a / 2).addScaledVector(sideB, b / 2)
  ];
  const vertices = [...corners(start, a1, b1), ...corners(end, a2, b2)];
  const positions = new Float32Array(vertices.flatMap(point => point.toArray()));
  const indices = [
    0, 2, 1, 0, 3, 2,
    4, 5, 6, 4, 6, 7,
    0, 1, 5, 0, 5, 4,
    1, 2, 6, 1, 6, 5,
    2, 3, 7, 2, 7, 6,
    3, 0, 4, 3, 4, 7
  ];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}

function makeCylinderGeometry(member, fallbackRadius) {
  if (!member.start || !member.end || !(member.length > math.EPSILON)) return null;
  const diameterStart = member.sectionStart?.diameter;
  const diameterEnd = member.sectionEnd?.diameter;
  const radiusStart = Number.isFinite(diameterStart) && diameterStart > 0 ? diameterStart / 2 : fallbackRadius;
  const radiusEnd = Number.isFinite(diameterEnd) && diameterEnd > 0 ? diameterEnd / 2 : fallbackRadius;
  const geometry = new THREE.CylinderGeometry(radiusEnd, radiusStart, member.length, 20, 1, false);
  const axis = vector3(member.frame.axis);
  geometry.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis));
  geometry.translate(
    (member.start[0] + member.end[0]) / 2,
    (member.start[1] + member.end[1]) / 2,
    (member.start[2] + member.end[2]) / 2
  );
  return geometry;
}

class OpenFastHydroViewer {
  constructor(container) {
    if (!math) throw new Error('Morison geometry math module is not available.');
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xf3f7f6);
    this.perspectiveCamera = new THREE.PerspectiveCamera(40, 1, 0.01, 1e8);
    this.orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, -1e7, 1e7);
    this.camera = this.perspectiveCamera;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.setAttribute('aria-label', 'Morison XYZ geometry viewport');
    this.renderer.domElement.tabIndex = 0;
    this.container.appendChild(this.renderer.domElement);

    this.environmentGroup = new THREE.Group();
    this.geometryGroup = new THREE.Group();
    this.divisionGroup = new THREE.Group();
    this.scene.add(this.environmentGroup, this.geometryGroup, this.divisionGroup);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x647570, 2.1));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
    keyLight.position.set(5, -4, 8);
    this.scene.add(keyLight);

    this.labelLayer = document.createElement('div');
    this.labelLayer.className = 'hydro-geometry-label-layer';
    this.container.appendChild(this.labelLayer);
    this.tooltip = document.createElement('div');
    this.tooltip.className = 'hydro-geometry-tooltip';
    this.tooltip.hidden = true;
    this.container.appendChild(this.tooltip);

    this.raycaster = new THREE.Raycaster();
    this.raycaster.params.Points.threshold = 1;
    this.pointer = new THREE.Vector2();
    this.pickables = [];
    this.memberVisuals = new Map();
    this.jointVisuals = new Map();
    this.labels = [];
    this.target = new THREE.Vector3();
    this.baseRadius = 10;
    this.radius = 15;
    this.orthoHeight = 20;
    this.yaw = Math.PI * 0.78;
    this.pitch = Math.PI * 0.25;
    this.viewMode = '3d';
    this.selectedMemberId = null;
    this.selectedJointId = null;
    this.layers = { labels: true, water: true, seabed: false, wave: true, divisions: false };
    this.modelKey = '';
    this.hasModel = false;
    this.drag = null;
    this.pendingFrame = 0;

    this.bindControls();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  bindControls() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener('contextmenu', event => event.preventDefault());
    canvas.addEventListener('pointerdown', event => {
      canvas.setPointerCapture(event.pointerId);
      this.drag = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        lastX: event.clientX,
        lastY: event.clientY,
        moved: false,
        mode: event.button === 2 || event.shiftKey || this.viewMode !== '3d' ? 'pan' : 'orbit'
      };
    });
    canvas.addEventListener('pointermove', event => {
      if (!this.drag) {
        this.updateHover(event);
        return;
      }
      const dx = event.clientX - this.drag.lastX;
      const dy = event.clientY - this.drag.lastY;
      if (Math.hypot(event.clientX - this.drag.x, event.clientY - this.drag.y) > 3) this.drag.moved = true;
      this.drag.lastX = event.clientX;
      this.drag.lastY = event.clientY;
      if (this.drag.mode === 'orbit') {
        this.yaw -= dx * 0.008;
        this.pitch = THREE.MathUtils.clamp(this.pitch + dy * 0.007, -1.48, 1.48);
      } else {
        this.pan(dx, dy);
      }
      this.updateCamera();
    });
    const finish = event => {
      if (!this.drag || this.drag.pointerId !== event.pointerId) return;
      const wasMoved = this.drag.moved;
      this.drag = null;
      if (!wasMoved) this.pick(event);
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', () => { this.drag = null; });
    canvas.addEventListener('pointerleave', () => {
      if (!this.drag) this.hideTooltip();
    });
    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      const factor = Math.exp(event.deltaY * 0.001);
      if (this.viewMode === '3d') this.radius = THREE.MathUtils.clamp(this.radius * factor, this.baseRadius * 0.03, this.baseRadius * 100);
      else this.orthoHeight = THREE.MathUtils.clamp(this.orthoHeight * factor, this.baseRadius * 0.02, this.baseRadius * 100);
      this.updateCamera();
    }, { passive: false });
    canvas.addEventListener('dblclick', event => {
      event.preventDefault();
      this.fit();
    });
    canvas.addEventListener('keydown', event => {
      if (event.key.toLowerCase() === 'f') this.fit();
      if (event.key === 'Escape') {
        this.setSelection({ memberId: null, jointId: null });
        this.hideTooltip();
      }
    });
  }

  resize() {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(width, height, false);
    this.perspectiveCamera.aspect = width / height;
    this.perspectiveCamera.updateProjectionMatrix();
    this.updateOrthographicProjection();
    this.requestRender();
  }

  updateOrthographicProjection() {
    const aspect = Math.max(0.01, this.container.clientWidth / Math.max(1, this.container.clientHeight));
    const halfHeight = Math.max(this.orthoHeight / 2, 0.01);
    this.orthographicCamera.left = -halfHeight * aspect;
    this.orthographicCamera.right = halfHeight * aspect;
    this.orthographicCamera.top = halfHeight;
    this.orthographicCamera.bottom = -halfHeight;
    this.orthographicCamera.updateProjectionMatrix();
  }

  pan(dx, dy) {
    const height = Math.max(1, this.container.clientHeight);
    const worldHeight = this.viewMode === '3d'
      ? 2 * this.radius * Math.tan(THREE.MathUtils.degToRad(this.perspectiveCamera.fov / 2))
      : this.orthoHeight;
    const scale = worldHeight / height;
    const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 1);
    this.target.addScaledVector(right, -dx * scale).addScaledVector(up, dy * scale);
  }

  updateCamera() {
    if (this.viewMode === '3d') {
      this.camera = this.perspectiveCamera;
      const horizontal = Math.cos(this.pitch) * this.radius;
      this.camera.position.set(
        this.target.x + Math.cos(this.yaw) * horizontal,
        this.target.y + Math.sin(this.yaw) * horizontal,
        this.target.z + Math.sin(this.pitch) * this.radius
      );
      this.camera.up.set(0, 0, 1);
    } else {
      this.camera = this.orthographicCamera;
      const distance = Math.max(this.baseRadius * 4, 100);
      if (this.viewMode === 'xy') {
        this.camera.position.copy(this.target).add(new THREE.Vector3(0, 0, distance));
        this.camera.up.set(0, 1, 0);
      } else if (this.viewMode === 'xz') {
        this.camera.position.copy(this.target).add(new THREE.Vector3(0, -distance, 0));
        this.camera.up.set(0, 0, 1);
      } else {
        this.camera.position.copy(this.target).add(new THREE.Vector3(distance, 0, 0));
        this.camera.up.set(0, 0, 1);
      }
      this.updateOrthographicProjection();
    }
    this.camera.lookAt(this.target);
    this.camera.updateMatrixWorld();
    this.requestRender();
  }

  requestRender() {
    if (this.pendingFrame || this.disposed) return;
    this.pendingFrame = requestAnimationFrame(() => {
      this.pendingFrame = 0;
      this.render();
    });
  }

  render() {
    if (this.disposed) return;
    this.renderer.render(this.scene, this.camera);
    this.updateLabels();
  }

  pointerCoordinates(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    return rect;
  }

  intersectionAt(event) {
    this.pointerCoordinates(event);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    return this.raycaster.intersectObjects(this.pickables, false)[0] || null;
  }

  pick(event) {
    const intersection = this.intersectionAt(event);
    if (!intersection) return;
    const data = intersection.object.userData.hydroObject;
    if (!data) return;
    window.dispatchEvent(new CustomEvent('openfast-hydro-select', {
      detail: { kind: data.kind, id: data.id, referencedMemberIds: data.referencedMemberIds || [] }
    }));
  }

  updateHover(event) {
    const intersection = this.intersectionAt(event);
    const data = intersection?.object?.userData?.hydroObject;
    if (!data) {
      this.hideTooltip();
      return;
    }
    const rect = this.container.getBoundingClientRect();
    this.tooltip.textContent = this.tooltipText(data);
    this.tooltip.hidden = false;
    this.tooltip.style.left = `${Math.min(rect.width - 220, Math.max(8, event.clientX - rect.left + 12))}px`;
    this.tooltip.style.top = `${Math.min(rect.height - 84, Math.max(8, event.clientY - rect.top + 12))}px`;
  }

  tooltipText(data) {
    if (data.kind === 'joint') {
      const position = data.model.position.map(value => formatNumber(value)).join(', ');
      const members = data.model.referencedMemberIds.length ? data.model.referencedMemberIds.join(', ') : '—';
      return `Joint ${data.id} · XYZ (${position}) m · Members ${members}`;
    }
    const member = data.model;
    const shape = member.shape === 'rectangle' ? '矩形 / Rectangle' : '圆柱 / Cylinder';
    const status = member.issues.some(item => item.severity === 'error') ? ' · ERROR' : '';
    return `Member ${data.id} · ${shape} · L=${formatNumber(member.length)} m · J${member.startJointId}→J${member.endJointId}${status}`;
  }

  hideTooltip() {
    this.tooltip.hidden = true;
  }

  makeMemberVisual(member, markerRadius) {
    if (!member.start || !member.end || !member.frame || !(member.length > math.EPSILON)) return null;
    const geometry = member.shape === 'rectangle'
      ? makeRectangleGeometry(member)
      : makeCylinderGeometry(member, markerRadius * 0.55);
    if (!geometry) return null;
    const material = new THREE.MeshStandardMaterial({
      color: COLORS.normal,
      roughness: 0.7,
      metalness: 0.03,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.88,
      emissive: 0x000000
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.hydroObject = { kind: 'member', id: member.id, model: member };
    this.geometryGroup.add(mesh);
    this.pickables.push(mesh);

    const edgeGeometry = new THREE.EdgesGeometry(geometry, 24);
    const edgeMaterial = new THREE.LineBasicMaterial({ color: COLORS.edge, transparent: true, opacity: 0.72 });
    const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
    this.geometryGroup.add(edges);
    this.memberVisuals.set(member.id, { mesh, edges, model: member });

    if (member.internalPoints.length) {
      const divisionGeometry = new THREE.BufferGeometry().setFromPoints(member.internalPoints.map(vector3));
      const divisionMaterial = new THREE.PointsMaterial({ color: COLORS.division, size: 5, sizeAttenuation: false });
      const points = new THREE.Points(divisionGeometry, divisionMaterial);
      points.visible = this.layers.divisions;
      this.divisionGroup.add(points);
    }
    return mesh;
  }

  makeJointVisual(joint, markerRadius) {
    const geometry = new THREE.SphereGeometry(markerRadius, 16, 12);
    const material = new THREE.MeshStandardMaterial({ color: COLORS.joint, roughness: 0.6, emissive: 0x000000 });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.copy(vector3(joint.position));
    mesh.userData.hydroObject = { kind: 'joint', id: joint.id, model: joint, referencedMemberIds: joint.referencedMemberIds };
    this.geometryGroup.add(mesh);
    this.pickables.push(mesh);
    this.jointVisuals.set(joint.id, { mesh, model: joint });
  }

  rebuildGeometry() {
    clearGroup(this.geometryGroup);
    clearGroup(this.divisionGroup);
    this.pickables = [];
    this.memberVisuals.clear();
    this.jointVisuals.clear();
    this.clearLabels();
    if (!this.geometry) return;
    const diagonal = Math.max(vector3(this.geometry.bounds.max).distanceTo(vector3(this.geometry.bounds.min)), 1);
    const markerRadius = THREE.MathUtils.clamp(diagonal * 0.008, 0.12, 2.2);
    this.geometry.members.forEach(member => this.makeMemberVisual(member, markerRadius));
    this.geometry.joints.forEach(joint => this.makeJointVisual(joint, markerRadius));
    this.rebuildEnvironment();
    this.applySelection();
  }

  rebuildEnvironment() {
    clearGroup(this.environmentGroup);
    if (!this.geometry) return;
    const minimum = vector3(this.geometry.bounds.min);
    const maximum = vector3(this.geometry.bounds.max);
    const size = maximum.clone().sub(minimum);
    const extent = Math.max(size.x, size.y, 20) * 1.45;

    const waterMaterial = new THREE.MeshBasicMaterial({
      color: COLORS.water,
      transparent: true,
      opacity: 0.14,
      side: THREE.DoubleSide,
      depthWrite: false
    });
    const water = new THREE.Mesh(new THREE.PlaneGeometry(extent, extent), waterMaterial);
    water.position.set(this.target.x, this.target.y, 0);
    water.visible = this.layers.water;
    water.userData.layer = 'water';
    this.environmentGroup.add(water);
    const waterGrid = new THREE.GridHelper(extent, 12, 0x80aeb1, 0xc6dddc);
    waterGrid.rotation.x = Math.PI / 2;
    waterGrid.position.set(this.target.x, this.target.y, 0);
    waterGrid.material.transparent = true;
    waterGrid.material.opacity = 0.35;
    waterGrid.visible = this.layers.water;
    waterGrid.userData.layer = 'water';
    this.environmentGroup.add(waterGrid);

    const depth = Number(this.environment?.waterDepth);
    if (Number.isFinite(depth) && depth > 0) {
      const seabed = new THREE.Mesh(
        new THREE.PlaneGeometry(extent, extent),
        new THREE.MeshBasicMaterial({ color: COLORS.seabed, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false })
      );
      seabed.position.set(this.target.x, this.target.y, -depth);
      seabed.visible = this.layers.seabed;
      seabed.userData.layer = 'seabed';
      this.environmentGroup.add(seabed);
    }

    const axesSize = THREE.MathUtils.clamp(this.baseRadius * 0.2, 2, 18);
    const axes = new THREE.AxesHelper(axesSize);
    axes.position.set(0, 0, 0);
    this.environmentGroup.add(axes);
    this.addLabel(new THREE.Vector3(axesSize * 1.08, 0, 0), 'X', 'axis');
    this.addLabel(new THREE.Vector3(0, axesSize * 1.08, 0), 'Y', 'axis');
    this.addLabel(new THREE.Vector3(0, 0, axesSize * 1.08), 'Z', 'axis');

    const waveDirection = Number(this.environment?.waveDirectionDeg);
    if (Number.isFinite(waveDirection)) {
      const radians = THREE.MathUtils.degToRad(waveDirection);
      const direction = new THREE.Vector3(Math.cos(radians), Math.sin(radians), 0).normalize();
      const origin = new THREE.Vector3(this.target.x, this.target.y, Math.max(0.15, size.z * 0.02));
      const arrow = new THREE.ArrowHelper(direction, origin, Math.max(extent * 0.2, 8), 0x2e7185, Math.max(extent * 0.035, 1.5), Math.max(extent * 0.018, 0.8));
      arrow.visible = this.layers.wave;
      arrow.userData.layer = 'wave';
      this.environmentGroup.add(arrow);
      this.addLabel(origin.clone().addScaledVector(direction, Math.max(extent * 0.22, 9)), `Wave ${formatNumber(waveDirection, 1)}°`, 'wave');
    }
    this.refreshLabelVisibility();
  }

  addLabel(position, text, type, id = null) {
    const element = document.createElement('span');
    element.className = `hydro-geometry-label ${type}`;
    element.textContent = text;
    this.labelLayer.appendChild(element);
    this.labels.push({ position, element, type, id });
  }

  clearLabels() {
    this.labels = [];
    this.labelLayer.innerHTML = '';
  }

  rebuildObjectLabels() {
    this.labels.filter(label => !['axis', 'wave'].includes(label.type)).forEach(label => label.element.remove());
    this.labels = this.labels.filter(label => ['axis', 'wave'].includes(label.type));
    if (!this.geometry) return;
    for (const joint of this.geometry.joints) {
      this.addLabel(vector3(joint.position), `J${joint.id}`, 'joint', joint.id);
    }
    const selected = this.geometry.members.find(member => Number(member.id) === Number(this.selectedMemberId));
    if (selected?.start && selected?.end) {
      const middle = vector3(selected.start).add(vector3(selected.end)).multiplyScalar(0.5);
      this.addLabel(middle, `Member ${selected.id}`, 'member', selected.id);
    }
    this.refreshLabelVisibility();
  }

  refreshLabelVisibility() {
    for (const label of this.labels) {
      const visible = label.type === 'axis'
        || label.type === 'member'
        || label.type === 'joint' && this.layers.labels
        || label.type === 'wave' && this.layers.wave;
      label.element.hidden = !visible;
    }
    this.requestRender();
  }

  updateLabels() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    for (const label of this.labels) {
      if (label.element.hidden) continue;
      const projected = label.position.clone().project(this.camera);
      const behind = projected.z < -1 || projected.z > 1;
      label.element.style.display = behind ? 'none' : '';
      if (behind) continue;
      label.element.style.transform = `translate(-50%, -50%) translate(${(projected.x * 0.5 + 0.5) * width}px, ${(-projected.y * 0.5 + 0.5) * height}px)`;
    }
  }

  applySelection() {
    for (const [id, visual] of this.memberVisuals) {
      const hasError = visual.model.issues.some(item => item.severity === 'error');
      const selected = Number(id) === Number(this.selectedMemberId);
      const color = hasError ? COLORS.error : selected ? COLORS.selected : visual.model.propPot ? COLORS.potential : COLORS.normal;
      visual.mesh.material.color.setHex(color);
      visual.mesh.material.emissive.setHex(selected ? 0x4a210f : 0x000000);
      visual.mesh.material.opacity = selected ? 1 : 0.88;
      visual.edges.material.color.setHex(selected ? COLORS.selected : hasError ? COLORS.error : COLORS.edge);
      visual.edges.material.opacity = selected ? 1 : 0.68;
    }
    for (const [id, visual] of this.jointVisuals) {
      const hasError = visual.model.issues.some(item => item.severity === 'error');
      const selected = Number(id) === Number(this.selectedJointId);
      const color = hasError ? COLORS.error : selected ? COLORS.selected : visual.model.orphan ? COLORS.orphan : COLORS.joint;
      visual.mesh.material.color.setHex(color);
      visual.mesh.material.emissive.setHex(selected ? 0x4a210f : 0x000000);
      visual.mesh.scale.setScalar(selected ? 1.35 : 1);
    }
    this.rebuildObjectLabels();
    this.requestRender();
  }

  setModel(payload = {}) {
    const nextKey = String(payload.modelKey || '');
    const shouldFit = !this.hasModel || nextKey !== this.modelKey || Boolean(payload.resetView);
    this.modelKey = nextKey;
    this.environment = payload.environment || {};
    this.selectedMemberId = payload.selectedMemberId ?? null;
    this.selectedJointId = payload.selectedJointId ?? null;
    this.geometry = math.buildHydroGeometry(payload.tables || {}, {
      targetFormat: payload.targetFormat,
      maxDivisionMarkers: 2000
    });
    const minimum = vector3(this.geometry.bounds.min);
    const maximum = vector3(this.geometry.bounds.max);
    const centre = minimum.clone().add(maximum).multiplyScalar(0.5);
    const diagonal = Math.max(maximum.distanceTo(minimum), 1);
    if (shouldFit) this.target.copy(centre);
    this.baseRadius = diagonal;
    this.perspectiveCamera.near = Math.max(diagonal / 100000, 0.001);
    this.perspectiveCamera.far = Math.max(diagonal * 1000, 1000);
    this.perspectiveCamera.updateProjectionMatrix();
    this.rebuildGeometry();
    this.hasModel = true;
    if (shouldFit) this.fit();
    else this.updateCamera();
    window.dispatchEvent(new CustomEvent('openfast-hydro-geometry-updated', {
      detail: {
        memberCount: this.geometry.members.length,
        jointCount: this.geometry.joints.length,
        issues: this.geometry.issues
      }
    }));
    return this.geometry;
  }

  setSelection({ memberId = null, jointId = null } = {}) {
    this.selectedMemberId = memberId;
    this.selectedJointId = jointId;
    this.applySelection();
  }

  setView(mode) {
    if (!['3d', 'xy', 'xz', 'yz'].includes(mode)) return;
    this.viewMode = mode;
    this.fit();
  }

  setLayers(next = {}) {
    Object.assign(this.layers, next);
    this.environmentGroup.traverse(object => {
      if (object.userData.layer && object.userData.layer in this.layers) object.visible = Boolean(this.layers[object.userData.layer]);
    });
    this.divisionGroup.visible = this.layers.divisions;
    this.refreshLabelVisibility();
    this.requestRender();
  }

  fit() {
    if (!this.geometry) return;
    const minimum = vector3(this.geometry.bounds.min);
    const maximum = vector3(this.geometry.bounds.max);
    this.target.copy(minimum).add(maximum).multiplyScalar(0.5);
    const size = maximum.clone().sub(minimum);
    this.baseRadius = Math.max(size.length(), 1);
    this.radius = this.baseRadius * 1.55;
    if (this.viewMode === 'xy') this.orthoHeight = Math.max(size.y, size.x / Math.max(0.2, this.container.clientWidth / Math.max(1, this.container.clientHeight)), 1) * 1.28;
    else if (this.viewMode === 'xz') this.orthoHeight = Math.max(size.z, size.x / Math.max(0.2, this.container.clientWidth / Math.max(1, this.container.clientHeight)), 1) * 1.28;
    else if (this.viewMode === 'yz') this.orthoHeight = Math.max(size.z, size.y / Math.max(0.2, this.container.clientWidth / Math.max(1, this.container.clientHeight)), 1) * 1.28;
    this.updateCamera();
  }

  reset() {
    this.yaw = Math.PI * 0.78;
    this.pitch = Math.PI * 0.25;
    this.fit();
  }

  dispose() {
    this.disposed = true;
    if (this.pendingFrame) cancelAnimationFrame(this.pendingFrame);
    this.resizeObserver.disconnect();
    clearGroup(this.environmentGroup);
    clearGroup(this.geometryGroup);
    clearGroup(this.divisionGroup);
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labelLayer.remove();
    this.tooltip.remove();
  }
}

let viewer = null;
let lastError = null;

window.OpenFastHydroGeometry = {
  mount(container) {
    if (!container) return null;
    if (viewer?.container === container) return viewer;
    viewer?.dispose();
    try {
      viewer = new OpenFastHydroViewer(container);
      lastError = null;
      return viewer;
    } catch (error) {
      lastError = error;
      viewer = null;
      return null;
    }
  },
  setModel(payload) {
    if (!viewer) return null;
    return viewer.setModel(payload);
  },
  setSelection(selection) {
    viewer?.setSelection(selection);
  },
  setView(mode) {
    viewer?.setView(mode);
  },
  setLayers(layers) {
    viewer?.setLayers(layers);
  },
  fit() {
    viewer?.fit();
  },
  reset() {
    viewer?.reset();
  },
  dispose() {
    viewer?.dispose();
    viewer = null;
  },
  getError() {
    return lastError;
  }
};

window.dispatchEvent(new CustomEvent('openfast-hydro-ready'));
