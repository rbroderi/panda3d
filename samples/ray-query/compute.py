"""Ray queries in a compute shader, with the hit triangle's corners fetched.

    python compute.py

Casts a ray straight down from each point of a 128x128 grid over boxes on a
ground plane, in a compute shader (GL_EXT_ray_query and
GL_EXT_ray_tracing_position_fetch), writing each hit's distance, its
triangle's normal (from its corners, placed in the world) and which
instance it hit to an image; then checks every texel against the boxes on
the CPU.  Exits with status 1 on any mismatch.
"""

import random
import struct
import sys

from panda3d.core import ComputeNode
from panda3d.core import Geom
from panda3d.core import GeomTriangles
from panda3d.core import GeomVertexData
from panda3d.core import GeomVertexFormat
from panda3d.core import GeomVertexWriter
from panda3d.core import LMatrix4
from panda3d.core import NodePath
from panda3d.core import RayTraceMesh
from panda3d.core import RayTraceScene
from panda3d.core import Shader
from panda3d.core import ShaderAttrib
from panda3d.core import Texture
from panda3d.core import loadPrcFileData

loadPrcFileData("", "load-display p3vulkandisplay\nwindow-type offscreen\nwin-size 64 64")
from direct.showbase.ShowBase import ShowBase  # noqa: E402

SIZE = 128
SPAN = 12.0  # the grid covers -SPAN..SPAN in x and y
TOP = 10.0  # rays start this high

COMPUTE = f"""#version 460
#extension GL_EXT_ray_query : require
#extension GL_EXT_ray_tracing_position_fetch : require
layout(local_size_x = 8, local_size_y = 8) in;
uniform accelerationStructureEXT scene;
layout(rgba32f) uniform writeonly image2D hits;
void main() {{
  ivec2 at = ivec2(gl_GlobalInvocationID.xy);
  vec2 xy = ((vec2(at) + 0.5) / {SIZE}.0 * 2.0 - 1.0) * {SPAN};
  rayQueryEXT q;
  rayQueryInitializeEXT(q, scene, gl_RayFlagsOpaqueEXT, 0xFF,
                        vec3(xy, {TOP}), 0.0, vec3(0.0, 0.0, -1.0), 100.0);
  while (rayQueryProceedEXT(q)) {{}}
  vec4 result = vec4(-1.0);
  if (rayQueryGetIntersectionTypeEXT(q, true) != gl_RayQueryCommittedIntersectionNoneEXT) {{
    vec3 corners[3];
    rayQueryGetIntersectionTriangleVertexPositionsEXT(q, true, corners);
    mat4x3 to_world = rayQueryGetIntersectionObjectToWorldEXT(q, true);
    vec3 a = to_world * vec4(corners[0], 1.0);
    vec3 b = to_world * vec4(corners[1], 1.0);
    vec3 c = to_world * vec4(corners[2], 1.0);
    vec3 n = normalize(cross(b - a, c - a));
    result = vec4(rayQueryGetIntersectionTEXT(q, true), n.z,
                  float(rayQueryGetIntersectionInstanceCustomIndexEXT(q, true)), 0.0);
  }}
  imageStore(hits, at, result);
}}
"""


def make_cube() -> Geom:
    """A unit cube from (0, 0, 0) to (1, 1, 1)."""
    vdata = GeomVertexData("cube", GeomVertexFormat.get_v3(), Geom.UH_static)
    vertex = GeomVertexWriter(vdata, "vertex")
    for i in range(8):
        vertex.add_data3(i & 1, (i >> 1) & 1, (i >> 2) & 1)
    tris = GeomTriangles(Geom.UH_static)
    # Each face counter-clockwise from outside.
    for a, b, c, d in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
        tris.add_vertices(a, b, c)
        tris.add_vertices(a, c, d)
    geom = Geom(vdata)
    geom.add_primitive(tris)
    return geom


base = ShowBase()
cube = RayTraceMesh("cube")
cube.add_geom(make_cube())
scene = RayTraceScene("compute scene")
# The ground: a flat cube 0.5 deep, its top at z = 0.
scene.add_instance(cube, LMatrix4.scale_mat(2 * SPAN, 2 * SPAN, 0.5) * LMatrix4.translate_mat(-SPAN, -SPAN, -0.5), custom_index=0)
rng = random.Random(3)
boxes = []
for i in range(30):
    sx, sy, sz = rng.choice((1, 2, 3)), rng.choice((1, 2)), rng.uniform(0.5, 5)
    x, y = rng.uniform(-11, 8), rng.uniform(-11, 9)
    scene.add_instance(cube, LMatrix4.scale_mat(sx, sy, sz) * LMatrix4.translate_mat(x, y, 0), custom_index=i + 1)
    boxes.append((x, y, x + sx, y + sy, sz))

hits = Texture("hits")
hits.setup_2d_texture(SIZE, SIZE, Texture.T_float, Texture.F_rgba32)
hits.set_clear_color((0, 0, 0, 0))

node = NodePath(ComputeNode("rays"))
node.set_shader(Shader.make_compute(Shader.SL_GLSL, COMPUTE))
node.set_shader_input("scene", scene)
node.set_shader_input("hits", hits)
base.graphicsEngine.dispatch_compute((SIZE // 8, SIZE // 8, 1), node.get_attrib(ShaderAttrib), base.win.get_gsg())
base.graphicsEngine.extract_texture_data(hits, base.win.get_gsg())
data = bytes(hits.get_ram_image())

bad = 0
EDGE = 1e-3
for py in range(SIZE):
    for px in range(SIZE):
        # Panda keeps RAM images as BGRA.
        index, nz, t, _ = struct.unpack_from("4f", data, (py * SIZE + px) * 16)
        x = ((px + 0.5) / SIZE * 2 - 1) * SPAN
        y = ((py + 0.5) / SIZE * 2 - 1) * SPAN
        tops = [(b[4], i + 1) for i, b in enumerate(boxes)
                if b[0] - EDGE <= x <= b[2] + EDGE and b[1] - EDGE <= y <= b[3] + EDGE]
        near_edge = any(min(abs(x - b[0]), abs(x - b[2]), abs(y - b[1]), abs(y - b[3])) < 0.02
                        for b in boxes)
        top, want = max(tops, default=(0.0, 0))
        ok = abs(t - (TOP - top)) < 1e-3 and abs(nz - 1.0) < 1e-3 and int(index) == want
        if not ok and not near_edge:
            bad += 1
            if bad <= 5:
                print("mismatch at", (px, py), "got", (t, nz, index), "want", (TOP - top, 1.0, want))
print(f"{SIZE * SIZE} rays, {bad} mismatched", flush=True)
sys.exit(1 if bad else 0)
