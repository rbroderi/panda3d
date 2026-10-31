"""Ray-traced hard shadows with GL_EXT_ray_query on the Vulkan renderer.

    python shadows.py [--check] [--boxes N] [--size WxH] [--frames N]

Voxel boxes stand on a ground plane under a point light.  Their triangles go
into one RayTraceMesh (a unit cube) and one for the ground; a RayTraceScene
places an instance per box.  The fragment shader traces one ray per pixel
from the surface to the light and darkens the pixel if anything is hit.

--check renders the ground from straight above with an orthographic lens,
computes the same shadows on the CPU (ray against box), prints how many
ground pixels disagree, and exits with status 1 if more than 0.5% do.
Without it, the window stays open and the boxes bob up and down, which
rebuilds the scene's top-level structure every frame.
"""

import argparse
import math
import random
import sys
import time

from panda3d.core import Filename
from panda3d.core import Geom
from panda3d.core import GeomNode
from panda3d.core import GeomTriangles
from panda3d.core import GeomVertexData
from panda3d.core import GeomVertexFormat
from panda3d.core import GeomVertexWriter
from panda3d.core import LPoint3
from panda3d.core import OrthographicLens
from panda3d.core import RayTraceMesh
from panda3d.core import RayTraceScene
from panda3d.core import Shader
from panda3d.core import loadPrcFileData

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
parser.add_argument("--boxes", type=int, default=24)
parser.add_argument("--size", default="512x512")
parser.add_argument("--frames", type=int, default=0, help="time this many frames, then exit")
parser.add_argument("--no-rays", action="store_true", help="same shader without the ray query")
parser.add_argument("--rays", type=int, default=1, help="shadow rays per pixel (soft shadows if > 1)")
parser.add_argument("--bench", action="store_true", help="alternate ray counts and moving/still boxes in one run; print medians")
parser.add_argument("--extra", type=int, default=0, help="instances in the scene that are not drawn (below the ground)")
parser.add_argument("--still", action="store_true", help="don't move the boxes (no rebuilds)")
args = parser.parse_args()
width, height = (int(v) for v in args.size.split("x"))

loadPrcFileData("", f"load-display p3vulkandisplay\nwin-size {width} {height}\nsync-video 0")
from direct.showbase.ShowBase import ShowBase  # noqa: E402

LIGHT = LPoint3(6, -2, 9)
GROUND = 12.0  # half-size of the ground square

VERT = """#version 460
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
out vec3 world_pos;
out vec3 world_normal;
void main() {
  gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
  world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
  world_normal = mat3(p3d_ModelMatrix) * p3d_Normal;
}
"""

FRAG = """#version 460
#extension GL_EXT_ray_query : require
uniform accelerationStructureEXT scene;
uniform vec3 light_pos;
uniform vec4 p3d_ColorScale;
uniform int use_rays;
uniform float light_radius;
in vec3 world_pos;
in vec3 world_normal;
out vec4 color;
void main() {
  vec3 n = normalize(world_normal);
  vec3 to_light = light_pos - world_pos;
  float dist = length(to_light);
  vec3 l = to_light / dist;
  float lit = max(dot(n, l), 0.0);
  if (lit > 0.0 && use_rays > 0) {
    // use_rays rays to points on a sphere round the light (one: its centre).
    float seen = 0.0;
    for (int i = 0; i < use_rays; i++) {
      vec3 target = light_pos;
      if (use_rays > 1) {
        float a = 6.2831853 * fract(float(i) * 0.618034 + dot(gl_FragCoord.xy, vec2(0.0671, 0.0583)));
        float z = 1.0 - 2.0 * (float(i) + 0.5) / float(use_rays);
        float r = sqrt(1.0 - z * z);
        target += light_radius * vec3(r * cos(a), r * sin(a), z);
      }
      vec3 d = target - world_pos;
      float len = length(d);
      rayQueryEXT q;
      rayQueryInitializeEXT(q, scene,
        gl_RayFlagsTerminateOnFirstHitEXT | gl_RayFlagsOpaqueEXT, 0xFF,
        world_pos + n * 0.002, 0.0, d / len, len);
      while (rayQueryProceedEXT(q)) {}
      if (rayQueryGetIntersectionTypeEXT(q, true) == gl_RayQueryCommittedIntersectionNoneEXT) {
        seen += 1.0;
      }
    }
    lit *= seen / float(use_rays);
  }
  color = vec4(p3d_ColorScale.rgb * (0.15 + 0.85 * lit), 1.0);
}
"""


def make_cube() -> Geom:
    """A unit cube from (0, 0, 0) to (1, 1, 1), with flat normals."""
    vdata = GeomVertexData("cube", GeomVertexFormat.get_v3n3(), Geom.UH_static)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UH_static)
    faces = [
        ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
        ((-1, 0, 0), [(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)]),
        ((0, 1, 0), [(1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)]),
        ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
        ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
        ((0, 0, -1), [(0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0)]),
    ]
    for i, (n, corners) in enumerate(faces):
        for c in corners:
            vertex.add_data3(*c)
            normal.add_data3(*n)
        tris.add_vertices(4 * i, 4 * i + 1, 4 * i + 2)
        tris.add_vertices(4 * i, 4 * i + 2, 4 * i + 3)
    geom = Geom(vdata)
    geom.add_primitive(tris)
    return geom


def make_ground() -> Geom:
    vdata = GeomVertexData("ground", GeomVertexFormat.get_v3n3(), Geom.UH_static)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        vertex.add_data3(x * GROUND, y * GROUND, 0)
        normal.add_data3(0, 0, 1)
    tris = GeomTriangles(Geom.UH_static)
    tris.add_vertices(0, 1, 2)
    tris.add_vertices(0, 2, 3)
    geom = Geom(vdata)
    geom.add_primitive(tris)
    return geom


base = ShowBase()
base.disable_mouse()
base.set_background_color(0.1, 0.1, 0.15, 1)

cube_geom = make_cube()
ground_geom = make_ground()
cube_mesh = RayTraceMesh("cube")
cube_mesh.add_geom(cube_geom)
ground_mesh = RayTraceMesh("ground")
ground_mesh.add_geom(ground_geom)

scene = RayTraceScene("shadow scene")
root = base.render.attach_new_node("scene")
ground_node = root.attach_new_node(GeomNode("ground"))
ground_node.node().add_geom(ground_geom)
ground_node.set_color_scale(0.8, 0.8, 0.75, 1)
scene.add_instance(ground_mesh, ground_node.get_mat(base.render))

rng = random.Random(7)
boxes = []  # (node, instance index, base z, (x0, y0, z0, x1, y1, z1) as built)
for i in range(args.boxes):
    sx, sy, sz = rng.choice((1, 2)), rng.choice((1, 2)), rng.choice((1, 2, 3, 4))
    x, y = rng.randint(-10, 8), rng.randint(-10, 8)
    node = root.attach_new_node(GeomNode(f"box{i}"))
    node.node().add_geom(cube_geom)
    node.set_pos(x, y, 0)
    node.set_scale(sx, sy, sz)
    node.set_color_scale(rng.uniform(0.4, 1), rng.uniform(0.4, 1), rng.uniform(0.4, 1), 1)
    index = scene.add_instance(cube_mesh, node.get_mat(base.render))
    boxes.append((node, index, (x, y, 0, x + sx, y + sy, sz)))

from panda3d.core import LMatrix4

extra = []  # (instance index, x, y): cubes far below the ground, never drawn
for i in range(args.extra):
    x, y = rng.uniform(-50, 50), rng.uniform(-50, 50)
    extra.append((scene.add_instance(cube_mesh, LMatrix4.translate_mat(x, y, -100)), x, y))

root.set_shader(Shader.make(Shader.SL_GLSL, VERT, FRAG))
root.set_shader_input("scene", scene)
root.set_shader_input("light_pos", LIGHT)
root.set_shader_input("use_rays", 0 if args.no_rays else args.rays)
root.set_shader_input("light_radius", 0.6)


def ray_hits_box(origin, target, box) -> bool:
    """Slab test of the segment origin->target against an axis-aligned box."""
    x0, y0, z0, x1, y1, z1 = box
    t0, t1 = 0.0, 1.0
    for o, d, lo, hi in zip(origin, (target[i] - origin[i] for i in range(3)), (x0, y0, z0), (x1, y1, z1)):
        if abs(d) < 1e-12:
            if o < lo or o > hi:
                return False
            continue
        a, b = (lo - o) / d, (hi - o) / d
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return True


if args.check:
    lens = OrthographicLens()
    lens.set_film_size(2 * GROUND, 2 * GROUND)
    lens.set_near_far(1, 100)
    base.cam.node().set_lens(lens)
    base.camera.set_pos(0, 0, 50)
    base.camera.set_hpr(0, -90, 0)  # looking down, +y up the image
    for _ in range(4):
        base.graphicsEngine.render_frame()
    name = "ray_query_check.png"
    base.win.save_screenshot(Filename.from_os_specific(name))
    from PIL import Image

    img = Image.open(name).convert("RGB")
    ground_px = mismatches = shadowed = 0
    for py in range(0, img.height, 2):
        for px in range(0, img.width, 2):
            # Pixel centre to world: +x right, +y up the image (camera looks down -z, up +y).
            wx = ((px + 0.5) / img.width * 2 - 1) * GROUND
            wy = (1 - (py + 0.5) / img.height * 2) * GROUND
            if any(b[0] <= wx <= b[3] and b[1] <= wy <= b[4] for _, _, b in boxes):
                continue  # a box top, not ground
            ground_px += 1
            expect = any(ray_hits_box((wx, wy, 0.002), LIGHT, b) for _, _, b in boxes)
            shadowed += expect
            # Ground colour 0.8 * (0.15 + 0.85 * lit): lit is >= 0.5 here, shadow ~0.12.
            got = img.getpixel((px, py))[0] < 60
            mismatches += expect != got
    print(f"ground pixels {ground_px}, expected in shadow {shadowed}, mismatched {mismatches} "
          f"({100 * mismatches / max(ground_px, 1):.2f}%)", flush=True)
    sys.exit(1 if mismatches > 0.005 * ground_px else 0)

base.camera.set_pos(-22, -30, 24)
base.camera.look_at(0, 0, 1)
start = time.perf_counter()
frame_times: list[float] = []
update_time = [0.0]


def bob(task):
    t = time.perf_counter() - start
    if not args.still:
        for node, index, _ in boxes:
            node.set_z(0.5 + 0.5 * math.sin(t * 2 + index))
            scene.set_instance_transform(index, node.get_mat(base.render))
        if len(frame_times) > 30:
            update_time[0] += time.perf_counter() - start - t
    frame_times.append(time.perf_counter())
    if args.frames and len(frame_times) > args.frames + 30:
        span = frame_times[-1] - frame_times[30]
        print(f"{args.frames} frames, {1000 * span / args.frames:.2f} ms/frame, "
              f"python update {1000 * update_time[0] / args.frames:.2f} ms/frame", flush=True)
        sys.exit(0)
    return task.cont


# --bench: windows of WINDOW frames, each with one setting, in turn, ROUNDS
# times; the median frame time of each setting (its first frames dropped).
SETTINGS = [(rays, moving) for moving in (False, True) for rays in (0, 1, 4, 16)]
WINDOW, SKIP, ROUNDS = 90, 20, 5
bench: dict[tuple[int, bool], list[float]] = {s: [] for s in SETTINGS}
bench_state = {"frame": 0, "last": 0.0}
bench_update: list[float] = []


def bench_task(task):
    n = bench_state["frame"]
    window = n // WINDOW
    if window >= len(SETTINGS) * ROUNDS:
        import statistics

        for (rays, moving), times in bench.items():
            print(f"rays {rays:2d} {'moving' if moving else 'still '}: "
                  f"median {1000 * statistics.median(times):.2f} ms, "
                  f"mean {1000 * statistics.mean(times):.2f} ms", flush=True)
        print(f"python update when moving: median {1000 * statistics.median(bench_update):.2f} ms", flush=True)
        sys.exit(0)
    rays, moving = SETTINGS[window % len(SETTINGS)]
    now = time.perf_counter()
    if n % WINDOW >= SKIP:
        bench[(rays, moving)].append(now - bench_state["last"])
    bench_state["last"] = now
    bench_state["frame"] = n + 1
    root.set_shader_input("use_rays", rays)
    if moving:
        t = now - start
        for node, index, _ in boxes:
            node.set_z(0.5 + 0.5 * math.sin(t * 2 + index))
            scene.set_instance_transform(index, node.get_mat(base.render))
        for index, x, y in extra:
            scene.set_instance_transform(index, LMatrix4.translate_mat(x, y, -100 + math.sin(t + index)))
        bench_update.append(time.perf_counter() - now)
    return task.cont


base.task_mgr.add(bench_task if args.bench else bob, "bob")
base.run()
