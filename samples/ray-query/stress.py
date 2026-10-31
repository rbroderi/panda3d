"""Ray queries over a scene that keeps changing, for a few thousand frames.

    python stress.py [--frames N] [--swap-every N] [--meshes N] [--copy]
                     [--render] [--threaded]

Builds meshes of interleaved, wide-format Geoms (like a game's models), and
each frame moves every instance (the scene is refitted) and draws a card
whose fragment shader traces a shadow ray per pixel against the scene.
Every few frames some meshes are swapped for new ones (new Geoms: their
old structures are released, new ones built and then compacted).  The
meshes are built straight from the Geoms' own buffers, or with --copy from
copies (ray-trace-reference-geoms false); --render draws the Geoms too, and
--threaded uses the Cull/Draw threading model, where a new Geom reaches the
draw thread a frame or two after it is made.  Exits with status 0 if it got
through all its frames, 1 if the device was lost.

It found two bugs: reading a new query pool's compacted size before the
frame that reset it was done (a corrupt compacted structure), and building
from a Geom before the draw thread could see it (with --threaded).  Each
lost the device on an AMD 780M within a few hundred frames.
"""

import argparse
import math
import random
import sys

from panda3d.core import CardMaker
from panda3d.core import Geom
from panda3d.core import GeomEnums
from panda3d.core import GeomNode
from panda3d.core import GeomTriangles
from panda3d.core import GeomVertexArrayFormat
from panda3d.core import GeomVertexData
from panda3d.core import GeomVertexFormat
from panda3d.core import GeomVertexWriter
from panda3d.core import LMatrix4
from panda3d.core import NodePath
from panda3d.core import RayTraceMesh
from panda3d.core import RayTraceScene
from panda3d.core import Shader
from panda3d.core import loadPrcFileData

parser = argparse.ArgumentParser()
parser.add_argument("--frames", type=int, default=3000)
parser.add_argument("--swap-every", type=int, default=20)
parser.add_argument("--meshes", type=int, default=60)
parser.add_argument("--copy", action="store_true", help="build from copies of the Geoms")
parser.add_argument("--render", action="store_true", help="also draw the meshes' Geoms")
parser.add_argument("--threaded", action="store_true", help="threading-model Cull/Draw")
args = parser.parse_args()

loadPrcFileData("", "load-display p3vulkandisplay\nwindow-type offscreen\nwin-size 512 512\n"
                    f"ray-trace-reference-geoms {'false' if args.copy else 'true'}\n"
                    + ("threading-model Cull/Draw" if args.threaded else ""))
from direct.showbase.ShowBase import ShowBase  # noqa: E402

base = ShowBase()
gsg = base.win.get_gsg()
if not gsg.get_supports_ray_query():
    print("no ray queries here")
    sys.exit(0)

# A wide interleaved format: 76 bytes a vertex, the position first.
array = GeomVertexArrayFormat()
array.add_column("vertex", 3, Geom.NT_float32, Geom.C_point)
array.add_column("normal", 3, Geom.NT_float32, Geom.C_normal)
array.add_column("texcoord", 2, Geom.NT_float32, Geom.C_texcoord)
array.add_column("tangent", 3, Geom.NT_float32, Geom.C_vector)
array.add_column("binormal", 3, Geom.NT_float32, Geom.C_vector)
array.add_column("color", 4, Geom.NT_float32, Geom.C_color)
array.add_column("extra", 1, Geom.NT_float32, Geom.C_other)
FORMAT = GeomVertexFormat.register_format(GeomVertexFormat(array))
rng = random.Random(1)


def make_geom(rings: int) -> Geom:
    """A lumpy sphere of about 2 * rings * rings triangles, indexed (uint32 if big)."""
    vdata = GeomVertexData("lump", FORMAT, GeomEnums.UH_static)
    segs = rings * 2
    vdata.unclean_set_num_rows((rings + 1) * (segs + 1))
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    bump = rng.uniform(0.0, 0.3)
    for i in range(rings + 1):
        lat = math.pi * i / rings
        for j in range(segs + 1):
            lon = 2 * math.pi * j / segs
            r = 1.0 + bump * math.sin(3 * lat) * math.cos(5 * lon)
            n = (math.sin(lat) * math.cos(lon), math.sin(lat) * math.sin(lon), math.cos(lat))
            vertex.set_data3(n[0] * r, n[1] * r, n[2] * r)
            normal.set_data3(*n)
    tris = GeomTriangles(GeomEnums.UH_static)
    if (rings + 1) * (segs + 1) > 65535:
        tris.set_index_type(GeomEnums.NT_uint32)
    for i in range(rings):
        for j in range(segs):
            a = i * (segs + 1) + j
            b = a + segs + 1
            tris.add_vertices(a, b, a + 1)
            tris.add_vertices(a + 1, b, b + 1)
    geom = Geom(vdata)
    geom.add_primitive(tris)
    return geom


def make_mesh() -> tuple[RayTraceMesh, NodePath]:
    """A mesh of a few Geoms, and (drawn, with --render) a node of the same Geoms."""
    mesh = RayTraceMesh("lump")
    node = GeomNode("lump")
    for _ in range(rng.randint(1, 4)):
        geom = make_geom(rng.randint(8, 48))
        mesh.add_geom(geom)
        node.add_geom(geom)
    path = NodePath(node)
    if args.render:
        path.reparent_to(base.render)
    return mesh, path


scene = RayTraceScene("stress")
meshes = [make_mesh() for _ in range(args.meshes)]
for i, (mesh, _) in enumerate(meshes):
    scene.add_instance(mesh, LMatrix4.ident_mat(), 0xFF, i)
base.cam.set_pos(0, -60, 0)
base.cam.look_at(0, 0, 0)

SHADER_V = """#version 460
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
uniform mat4 p3d_ModelViewProjectionMatrix;
out vec2 uv;
void main() { gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex; uv = p3d_MultiTexCoord0; }
"""
SHADER_F = """#version 460
#extension GL_EXT_ray_query : require
uniform accelerationStructureEXT scene;
in vec2 uv;
out vec4 color;
void main() {
  vec3 origin = vec3((uv - 0.5) * 40.0, -12.0);
  rayQueryEXT q;
  rayQueryInitializeEXT(q, scene, gl_RayFlagsOpaqueEXT, 0xFF, origin, 0.0, vec3(0.0, 0.0, 1.0), 100.0);
  while (rayQueryProceedEXT(q)) {}
  bool hit = rayQueryGetIntersectionTypeEXT(q, true) != gl_RayQueryCommittedIntersectionNoneEXT;
  color = hit ? vec4(1.0) : vec4(0.0, 0.0, 0.0, 1.0);
}
"""
cm = CardMaker("card")
cm.set_frame(-1, 1, -1, 1)
card = NodePath(cm.generate())
card.reparent_to(base.render2d)
card.set_shader(Shader.make(Shader.SL_GLSL, SHADER_V, SHADER_F))
card.set_shader_input("scene", scene)


def place(i: int, frame: int) -> LMatrix4:
    a = i * 2.399 + frame * 0.01
    r = 4.0 + (i % 7) * 2.0
    return LMatrix4.translate_mat(r * math.cos(a), r * math.sin(a), (i % 5) - 2.0)


lost = False
for frame in range(args.frames):
    for i, (_, path) in enumerate(meshes):
        mat = place(i, frame)
        scene.set_instance_transform(i, mat)
        path.set_mat(mat)
    if args.swap_every and frame % args.swap_every == args.swap_every - 1:
        for _ in range(3):
            i = rng.randrange(len(meshes))
            meshes[i][1].remove_node()
            meshes[i] = make_mesh()
            scene.set_instance_mesh(i, meshes[i][0])
    base.graphicsEngine.render_frame()
    if not gsg.is_valid() or gsg.needs_reset():
        lost = True
        break
    if frame % 500 == 0:
        print("frame", frame, flush=True)
print("frames", frame + 1, "lost" if lost else "ok", flush=True)
sys.exit(1 if lost else 0)
