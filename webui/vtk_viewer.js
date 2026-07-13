import * as THREE from './vendor/three.module.min.js';

class OpenFastVtkViewer {
  constructor(container) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xf3f6f7);
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1e8);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.container.appendChild(this.renderer.domElement);

    this.geometryGroup = new THREE.Group();
    this.scene.add(this.geometryGroup);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x6c7780, 2.2));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.6);
    keyLight.position.set(4, -3, 7);
    this.scene.add(keyLight);
    this.grid = new THREE.GridHelper(10, 20, 0x8fa1a7, 0xd3dcdf);
    this.grid.material.opacity = 0.48;
    this.grid.material.transparent = true;
    this.scene.add(this.grid);
    this.axes = new THREE.AxesHelper(2);
    this.scene.add(this.axes);

    this.target = new THREE.Vector3();
    this.radius = 12;
    this.yaw = Math.PI * 0.78;
    this.pitch = Math.PI * 0.28;
    this.drag = null;
    this.baseRadius = 12;
    this.bindControls();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
    this.updateCamera();
    this.animate();
  }

  bindControls() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener('pointerdown', event => {
      canvas.setPointerCapture(event.pointerId);
      this.drag = { x: event.clientX, y: event.clientY, yaw: this.yaw, pitch: this.pitch };
    });
    canvas.addEventListener('pointermove', event => {
      if (!this.drag) return;
      this.yaw = this.drag.yaw - (event.clientX - this.drag.x) * 0.008;
      this.pitch = THREE.MathUtils.clamp(this.drag.pitch + (event.clientY - this.drag.y) * 0.007, -1.48, 1.48);
      this.updateCamera();
    });
    const endDrag = () => { this.drag = null; };
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);
    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      this.radius = THREE.MathUtils.clamp(this.radius * Math.exp(event.deltaY * 0.001), this.baseRadius * 0.04, this.baseRadius * 80);
      this.updateCamera();
    }, { passive: false });
    canvas.addEventListener('dblclick', () => this.resetCamera());
  }

  resize() {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  updateCamera() {
    const horizontal = Math.cos(this.pitch) * this.radius;
    this.camera.position.set(
      this.target.x + Math.cos(this.yaw) * horizontal,
      this.target.y + Math.sin(this.yaw) * horizontal,
      this.target.z + Math.sin(this.pitch) * this.radius,
    );
    this.camera.up.set(0, 0, 1);
    this.camera.lookAt(this.target);
  }

  clearGeometry() {
    while (this.geometryGroup.children.length) {
      const child = this.geometryGroup.children.pop();
      child.geometry?.dispose();
      if (Array.isArray(child.material)) child.material.forEach(material => material.dispose());
      else child.material?.dispose();
    }
  }

  setGeometry(payload) {
    this.clearGeometry();
    const points = payload.points || [];
    const positions = new Float32Array(points.flat());
    if (!positions.length) throw new Error('VTK 文件没有可显示的点');

    if ((payload.triangles || []).length) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometry.setIndex((payload.triangles || []).flat());
      geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({
        color: 0x2c817c,
        roughness: 0.72,
        metalness: 0.04,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.88,
      });
      this.geometryGroup.add(new THREE.Mesh(geometry, material));
    }

    if ((payload.segments || []).length) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometry.setIndex((payload.segments || []).flat());
      const material = new THREE.LineBasicMaterial({ color: 0xb14134, transparent: true, opacity: 0.92 });
      this.geometryGroup.add(new THREE.LineSegments(geometry, material));
    }

    if (!(payload.triangles || []).length && !(payload.segments || []).length) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const material = new THREE.PointsMaterial({ color: 0x2c817c, size: 3, sizeAttenuation: false });
      this.geometryGroup.add(new THREE.Points(geometry, material));
    }

    const minimum = new THREE.Vector3(...(payload.bounds?.min || [0, 0, 0]));
    const maximum = new THREE.Vector3(...(payload.bounds?.max || [1, 1, 1]));
    this.target.copy(minimum).add(maximum).multiplyScalar(0.5);
    const size = maximum.clone().sub(minimum);
    this.baseRadius = Math.max(size.length(), 1);
    this.radius = this.baseRadius * 1.55;
    const gridSize = Math.max(size.x, size.y, 1) * 1.35;
    this.grid.scale.setScalar(gridSize / 10);
    this.grid.position.set(this.target.x, this.target.y, minimum.z);
    this.axes.position.copy(this.target);
    this.axes.scale.setScalar(this.baseRadius * 0.08);
    this.camera.near = Math.max(this.baseRadius / 100000, 0.001);
    this.camera.far = Math.max(this.baseRadius * 1000, 1000);
    this.camera.updateProjectionMatrix();
    this.resetCamera();
  }

  resetCamera() {
    this.yaw = Math.PI * 0.78;
    this.pitch = Math.PI * 0.28;
    this.radius = this.baseRadius * 1.55;
    this.updateCamera();
  }

  animate() {
    if (this.disposed) return;
    this.frame = requestAnimationFrame(() => this.animate());
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.resizeObserver.disconnect();
    this.clearGeometry();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

let viewer = null;

window.OpenFastVtk = {
  mount(container) {
    if (!viewer || viewer.container !== container) {
      viewer?.dispose();
      viewer = new OpenFastVtkViewer(container);
    }
    return viewer;
  },
  setGeometry(payload) {
    if (!viewer) throw new Error('VTK 查看器尚未挂载');
    viewer.setGeometry(payload);
  },
  reset() {
    viewer?.resetCamera();
  },
  dispose() {
    viewer?.dispose();
    viewer = null;
  },
};

window.dispatchEvent(new CustomEvent('openfast-vtk-ready'));
