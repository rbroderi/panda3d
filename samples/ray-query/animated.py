"""Ray queries against a skinned (animated) mesh, refitted as it moves.

    python animated.py

Poses Panda's walking panda, puts its Geoms in a RayTraceMesh (which copies
their triangles as posed), and casts a grid of rays at it from the front in
a compute shader; then checks every ray's hit or miss and distance against
the same posed triangles on the CPU.  Then poses it again further into the
walk, calls update_animation() (the structure is refitted) and checks again,
and that the two poses' hits differ.  Exits with status 1 on a failure.
"""

import struct
import sys

import numpy as np
from direct.actor.Actor import Actor
from panda3d.core import ComputeNode
from panda3d.core import GeomNode
from panda3d.core import GeomVertexReader
from panda3d.core import NodePath
from panda3d.core import RayTraceMesh
from panda3d.core import RayTraceScene
from panda3d.core import Shader
from panda3d.core import ShaderAttrib
from panda3d.core import Texture
from panda3d.core import Thread
from panda3d.core import loadPrcFileData

loadPrcFileData("", "load-display p3vulkandisplay\nwindow-type offscreen\nwin-size 64 64")
from direct.showbase.ShowBase import ShowBase  # noqa: E402

SIZE = 96

COMPUTE = f"""#version 460
#extension GL_EXT_ray_query : require
layout(local_size_x = 8, local_size_y = 8) in;
uniform accelerationStructureEXT scene;
layout(rgba32f) uniform writeonly image2D hits;
uniform vec4 box;  // x0, z0, x1, z1 of the grid
uniform float start_y;
void main() {{
  ivec2 at = ivec2(gl_GlobalInvocationID.xy);
  vec2 f = (vec2(at) + 0.5) / {SIZE}.0;
  vec3 origin = vec3(mix(box.x, box.z, f.x), start_y, mix(box.y, box.w, f.y));
  rayQueryEXT q;
  rayQueryInitializeEXT(q, scene, gl_RayFlagsOpaqueEXT, 0xFF, origin, 0.0,
                        vec3(0.0, -1.0, 0.0), 1e4);
  while (rayQueryProceedEXT(q)) {{}}
  float t = -1.0;
  if (rayQueryGetIntersectionTypeEXT(q, true) != gl_RayQueryCommittedIntersectionNoneEXT) {{
    t = rayQueryGetIntersectionTEXT(q, true);
  }}
  imageStore(hits, at, vec4(t, 0.0, 0.0, 1.0));
}}
"""

base = ShowBase()
gsg = base.win.get_gsg()
if not gsg.get_supports_ray_query():
    print("no ray queries here")
    sys.exit(0)

actor = Actor("panda-model", {"walk": "panda-walk4"})
actor.reparent_to(base.render)
geom_nodes = actor.find_all_matches("**/+GeomNode")
mesh = RayTraceMesh("panda")
for node_path in geom_nodes:
    node = node_path.node()
    assert isinstance(node, GeomNode)
    mat = node_path.get_mat(actor)
    for i in range(node.get_num_geoms()):
        mesh.add_geom(node.get_geom(i), mat)
print("animated", mesh.animated, "triangles", mesh.num_triangles, flush=True)
scene = RayTraceScene("panda scene")
scene.add_instance(mesh)

hits = Texture("hits")
hits.setup_2d_texture(SIZE, SIZE, Texture.T_float, Texture.F_rgba32)
compute = NodePath(ComputeNode("rays"))
compute.set_shader(Shader.make_compute(Shader.SL_GLSL, COMPUTE))
compute.set_shader_input("scene", scene)
compute.set_shader_input("hits", hits)


def posed_triangles() -> np.ndarray:
    """Return every triangle of the actor as posed now, (n, 3, 3), in its frame."""
    out = []
    thread = Thread.get_current_thread()
    for node_path in geom_nodes:
        node = node_path.node()
        mat = node_path.get_mat(actor)
        for i in range(node.get_num_geoms()):
            geom = node.get_geom(i).decompose()
            vdata = geom.get_vertex_data().animate_vertices(True, thread)
            reader = GeomVertexReader(vdata, "vertex")
            points = []
            while not reader.is_at_end():
                points.append(tuple(mat.xform_point(reader.get_data3())))
            points = np.array(points)
            for p in range(geom.get_num_primitives()):
                prim = geom.get_primitive(p).decompose()
                for t in range(prim.get_num_primitives()):
                    s = prim.get_primitive_start(t)
                    out.append(points[[prim.get_vertex(s), prim.get_vertex(s + 1), prim.get_vertex(s + 2)]])
    return np.array(out)


def cpu_hits(tris: np.ndarray, origins: np.ndarray) -> np.ndarray:
    """Closest hit distance of each ray along -y (Moller-Trumbore), -1 if none."""
    d = np.array([0.0, -1.0, 0.0])
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    result = np.full(len(origins), -1.0)
    for k, o in enumerate(origins):
        s = o - v0
        u = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, e1)
        v = (q @ d) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        if hit.any():
            result[k] = t[hit].min()
    return result


def check(label: str) -> tuple[int, np.ndarray]:
    """Trace the grid on the GPU and on the CPU; return mismatches and the GPU's."""
    actor.update(force=True)  # the joints, then the mesh posed by them
    mesh.update_animation()
    tris = posed_triangles()
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    box = (float(lo[0]), float(lo[2]), float(hi[0]), float(hi[2]))
    start_y = float(hi[1]) + 10.0
    compute.set_shader_input("box", box)
    compute.set_shader_input("start_y", start_y)
    base.graphicsEngine.dispatch_compute((SIZE // 8, SIZE // 8, 1), compute.get_attrib(ShaderAttrib), gsg)
    base.graphicsEngine.extract_texture_data(hits, gsg)
    data = bytes(hits.get_ram_image())
    gpu = np.array([struct.unpack_from("4f", data, i * 16)[2] for i in range(SIZE * SIZE)])  # BGRA: t is R
    ii, jj = np.meshgrid(np.arange(SIZE), np.arange(SIZE))
    f = (np.stack([ii.ravel(), jj.ravel()], 1) + 0.5) / SIZE
    origins = np.stack([box[0] + (box[2] - box[0]) * f[:, 0], np.full(len(f), start_y),
                        box[1] + (box[3] - box[1]) * f[:, 1]], 1)
    cpu = cpu_hits(tris, origins)
    scale = float(np.linalg.norm(hi - lo))
    bad = (np.sign(gpu) != np.sign(cpu)) | ((gpu > 0) & (np.abs(gpu - cpu) > 1e-3 * scale))
    print(f"{label}: {int((cpu > 0).sum())} of {len(cpu)} rays hit; "
          f"{int(bad.sum())} disagree ({100 * bad.mean():.2f}%)", flush=True)
    return int(bad.sum()), gpu


actor.pose("walk", 0)
bad0, first = check("pose 0")
actor.pose("walk", 12)
bad1, second = check("pose 12, refitted")
moved = int((np.abs(first - second) > 1e-4).sum())
print(f"rays whose hit moved between the poses: {moved}", flush=True)
# Silhouette rays may graze an edge either way: allow a few in a thousand.
limit = 0.005 * SIZE * SIZE
sys.exit(0 if bad0 <= limit and bad1 <= limit and moved > 0 else 1)
