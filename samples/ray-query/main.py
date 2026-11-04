#!/usr/bin/env python

"""
Ray-traced shadows with ray queries (Vulkan only)

Boxes bob up and down on the ground under a light that circles them.  The
shader traces a ray from each pixel to the light (GL_EXT_ray_query) against
a RayTraceScene holding the boxes and the ground, and darkens the pixel if
the ray hits anything.  With more than one ray to points round the light,
the shadows get soft edges.

This needs the Vulkan renderer, on a video card that supports
VK_KHR_ray_query.

Keys: 1, 2, 3 and 4 trace 0, 1, 4 or 16 rays a pixel; space pauses.
"""

import math
import random
import sys

from panda3d.core import loadPrcFileData

loadPrcFileData("", "load-display p3vulkandisplay")

from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import (  # noqa: E402
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LPoint3,
    RayTraceMesh,
    RayTraceScene,
    Shader,
    TextNode,
)

GROUND = 12.0  # half the size of the ground square

VERTEX = """#version 460
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

FRAGMENT = """#version 460
#extension GL_EXT_ray_query : require
uniform accelerationStructureEXT scene;
uniform vec3 light_pos;
uniform int rays;
uniform vec4 p3d_ColorScale;
in vec3 world_pos;
in vec3 world_normal;
out vec4 color;
void main() {
  vec3 n = normalize(world_normal);
  vec3 to_light = light_pos - world_pos;
  float lit = max(dot(n, normalize(to_light)), 0.0);
  if (lit > 0.0 && rays > 0) {
    // One ray to the light's centre, or several to points on a small
    // sphere round it, for soft shadows.
    float seen = 0.0;
    for (int i = 0; i < rays; ++i) {
      vec3 target = light_pos;
      if (rays > 1) {
        float a = 6.2831853 * fract(float(i) * 0.618034 + dot(gl_FragCoord.xy, vec2(0.0671, 0.0583)));
        float z = 1.0 - 2.0 * (float(i) + 0.5) / float(rays);
        float r = sqrt(1.0 - z * z);
        target += 0.6 * vec3(r * cos(a), r * sin(a), z);
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
    lit *= seen / float(rays);
  }
  color = vec4(p3d_ColorScale.rgb * (0.15 + 0.85 * lit), 1.0);
}
"""


def make_cube():
    """Returns a unit cube from (0, 0, 0) to (1, 1, 1), with flat normals."""
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
        for corner in corners:
            vertex.add_data3(*corner)
            normal.add_data3(*n)
        tris.add_vertices(4 * i, 4 * i + 1, 4 * i + 2)
        tris.add_vertices(4 * i, 4 * i + 2, 4 * i + 3)
    geom = Geom(vdata)
    geom.add_primitive(tris)
    return geom


def make_ground():
    """Returns a square on the ground, GROUND from the origin each way."""
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


class RayQueryDemo(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        if not self.win.get_gsg().get_supports_ray_query():
            print("This sample needs the Vulkan renderer, on a video card "
                  "that supports ray queries (VK_KHR_ray_query).")
            sys.exit(1)

        self.disable_mouse()
        self.set_background_color(0.1, 0.1, 0.15, 1)
        self.camera.set_pos(-22, -30, 24)
        self.camera.look_at(0, 0, 1)

        # The meshes rays are traced against: one cube, used for every box,
        # and the ground.  The scene places an instance of one per object.
        cube = make_cube()
        ground = make_ground()
        cube_mesh = RayTraceMesh("cube")
        cube_mesh.add_geom(cube)
        ground_mesh = RayTraceMesh("ground")
        ground_mesh.add_geom(ground)
        self.scene = RayTraceScene("shadows")

        self.root = self.render.attach_new_node("scene")
        ground_node = self.root.attach_new_node(GeomNode("ground"))
        ground_node.node().add_geom(ground)
        ground_node.set_color_scale(0.8, 0.8, 0.75, 1)
        self.scene.add_instance(ground_mesh, ground_node.get_mat(self.render))

        rng = random.Random(7)
        self.boxes = []
        for i in range(24):
            node = self.root.attach_new_node(GeomNode("box"))
            node.node().add_geom(cube)
            node.set_pos(rng.randint(-10, 8), rng.randint(-10, 8), 0)
            node.set_scale(rng.choice((1, 2)), rng.choice((1, 2)), rng.choice((1, 2, 3, 4)))
            node.set_color_scale(rng.uniform(0.4, 1), rng.uniform(0.4, 1), rng.uniform(0.4, 1), 1)
            index = self.scene.add_instance(cube_mesh, node.get_mat(self.render))
            self.boxes.append((node, index))

        self.root.set_shader(Shader.make(Shader.SL_GLSL, VERTEX, FRAGMENT))
        self.root.set_shader_input("scene", self.scene)
        self.root.set_shader_input("light_pos", LPoint3(6, -2, 9))
        self.root.set_shader_input("rays", 1)

        self.help = OnscreenText(
            text="1-4: 0, 1, 4 or 16 shadow rays a pixel\nspace: pause",
            parent=self.a2dTopLeft, align=TextNode.A_left, pos=(0.05, -0.08),
            scale=0.05, fg=(1, 1, 1, 1))
        for key, rays in (("1", 0), ("2", 1), ("3", 4), ("4", 16)):
            self.accept(key, self.root.set_shader_input, ["rays", rays])
        self.paused = False
        self.accept("space", self.toggle_pause)
        self.time = 0.0
        self.task_mgr.add(self.move, "move")

    def toggle_pause(self):
        self.paused = not self.paused

    def move(self, task):
        if not self.paused:
            self.time += self.clock.get_dt()
        t = self.time
        # The light circles; the boxes bob.  Moving instances only refits the
        # scene's structure, which is cheap.
        self.root.set_shader_input("light_pos", LPoint3(9 * math.cos(t * 0.3), 9 * math.sin(t * 0.3), 9))
        for node, index in self.boxes:
            node.set_z(0.5 + 0.5 * math.sin(t * 2 + index))
            self.scene.set_instance_transform(index, node.get_mat(self.render))
        return task.cont


demo = RayQueryDemo()
demo.run()
