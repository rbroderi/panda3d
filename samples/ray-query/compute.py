"""Ray queries in a compute shader, with the hit triangle's corners fetched.

    python compute.py

Casts a ray straight down from each point of a 128x128 grid over boxes on a
ground plane, in a compute shader (GL_EXT_ray_query and
GL_EXT_ray_tracing_position_fetch), writing each hit's distance, its
triangle's normal (from its corners, placed in the world) and which
instance it hit to an image; then checks every texel against the boxes on
the CPU.  It does so twice: dispatched by the engine between frames, and
by a ComputeNode drawn in the middle of a frame's rendering pass (between
two cards, which must both still show: the pass is ended for the dispatch
and resumed after).  Exits with status 1 on any mismatch.
"""

import random
import struct
import sys

from panda3d.core import CardMaker
from panda3d.core import ComputeNode
from panda3d.core import Geom
from panda3d.core import GeomTriangles
from panda3d.core import GeomVertexData
from panda3d.core import GeomVertexFormat
from panda3d.core import GeomVertexWriter
from panda3d.core import LMatrix4
from panda3d.core import NodePath
from panda3d.core import PNMImage
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
uniform float pass_tag;  // which dispatch wrote a texel
void main() {{
  ivec2 at = ivec2(gl_GlobalInvocationID.xy);
  vec2 xy = ((vec2(at) + 0.5) / {SIZE}.0 * 2.0 - 1.0) * {SPAN};
  rayQueryEXT q;
  rayQueryInitializeEXT(q, scene, gl_RayFlagsOpaqueEXT, 0xFF,
                        vec3(xy, {TOP}), 0.0, vec3(0.0, 0.0, -1.0), 100.0);
  while (rayQueryProceedEXT(q)) {{}}
  vec4 result = vec4(-1.0, -1.0, -1.0, pass_tag);
  if (rayQueryGetIntersectionTypeEXT(q, true) != gl_RayQueryCommittedIntersectionNoneEXT) {{
    vec3 corners[3];
    rayQueryGetIntersectionTriangleVertexPositionsEXT(q, true, corners);
    mat4x3 to_world = rayQueryGetIntersectionObjectToWorldEXT(q, true);
    vec3 a = to_world * vec4(corners[0], 1.0);
    vec3 b = to_world * vec4(corners[1], 1.0);
    vec3 c = to_world * vec4(corners[2], 1.0);
    vec3 n = normalize(cross(b - a, c - a));
    result = vec4(rayQueryGetIntersectionTEXT(q, true), n.z,
                  float(rayQueryGetIntersectionInstanceCustomIndexEXT(q, true)), pass_tag);
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

shader = Shader.make_compute(Shader.SL_GLSL, COMPUTE)
gsg = base.win.get_gsg()


def check(how: str, tag: float) -> int:
    """Read the hits back and count those that disagree with the boxes.

    Each must have been written by the dispatch tagged ``tag``.
    """
    base.graphicsEngine.extract_texture_data(hits, gsg)
    data = bytes(hits.get_ram_image())
    bad = 0
    for py in range(SIZE):
        for px in range(SIZE):
            bad += not hit_ok(data, px, py, tag)
    print(f"{how}: {SIZE * SIZE} rays, {bad} mismatched", flush=True)
    return bad


EDGE = 1e-3


def hit_ok(data: bytes, px: int, py: int, tag: float) -> bool:
    # Panda keeps RAM images as BGRA.
    index, nz, t, written = struct.unpack_from("4f", data, (py * SIZE + px) * 16)
    if written != tag:
        return False
    x = ((px + 0.5) / SIZE * 2 - 1) * SPAN
    y = ((py + 0.5) / SIZE * 2 - 1) * SPAN
    tops = [(b[4], i + 1) for i, b in enumerate(boxes)
            if b[0] - EDGE <= x <= b[2] + EDGE and b[1] - EDGE <= y <= b[3] + EDGE]
    near_edge = any(min(abs(x - b[0]), abs(x - b[2]), abs(y - b[1]), abs(y - b[3])) < 0.02
                    for b in boxes)
    top, want = max(tops, default=(0.0, 0))
    ok = abs(t - (TOP - top)) < 1e-3 and abs(nz - 1.0) < 1e-3 and int(index) == want
    return ok or near_edge


# 1. Dispatched by the engine, between frames.
node = NodePath(ComputeNode("rays"))
node.set_shader(shader)
node.set_shader_input("scene", scene)
node.set_shader_input("hits", hits)
node.set_shader_input("pass_tag", 1.0)
base.graphicsEngine.dispatch_compute((SIZE // 8, SIZE // 8, 1), node.get_attrib(ShaderAttrib), gsg)
bad = check("engine dispatch", 1.0)

# 2. A ComputeNode drawn between two cards, inside the window's rendering pass.
base.win.set_clear_color((1, 0, 0, 1))
cards = []
for i, (frame, color) in enumerate((((-1, 0, -1, 1), (0, 0, 1, 1)), ((0, 1, -1, 1), (0, 1, 0, 1)))):
    cm = CardMaker(f"card{i}")
    cm.set_frame(*frame)
    card = base.render2d.attach_new_node(cm.generate())
    card.set_color(*color)
    card.set_bin("fixed", 2 * i)
    cards.append(card)
compute = ComputeNode("rays in the frame")
compute.add_dispatch(SIZE // 8, SIZE // 8, 1)
drawn = base.render2d.attach_new_node(compute)
drawn.set_bin("fixed", 1)
drawn.set_shader(shader)
drawn.set_shader_input("scene", scene)
drawn.set_shader_input("hits", hits)
drawn.set_shader_input("pass_tag", 2.0)
for _ in range(3):
    base.graphicsEngine.render_frame()
drawn.remove_node()
base.graphicsEngine.render_frame()
bad += check("ComputeNode in the frame", 2.0)
image = PNMImage()
base.win.get_screenshot().store(image)
w, h = image.get_x_size(), image.get_y_size()
left, right = image.get_xel(w // 4, h // 2), image.get_xel(w * 3 // 4, h // 2)
print("cards seen:", [round(v, 2) for v in left], [round(v, 2) for v in right], flush=True)
bad += not (left[2] > 0.9 and left[0] < 0.1 and right[1] > 0.9 and right[0] < 0.1)
sys.exit(1 if bad else 0)
