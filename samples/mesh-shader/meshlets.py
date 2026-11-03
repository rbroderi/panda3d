"""A terrain of meshlets drawn by task and mesh shaders (VK_EXT_mesh_shader).

The terrain is a GRID x GRID grid of meshlets, each 8 x 8 quads (81 vertices,
128 triangles) of a height field computed in the mesh shader.  The task
shader tests each meshlet's bounding sphere against the view frustum and
launches mesh workgroups only for the ones in view, counting them in a
storage buffer.

    meshlets.py                 show it in a window for --seconds (20)
    meshlets.py --check         render with and without culling; compare
    meshlets.py --bench 300     time frames with and without culling

Use run.ps1 in this directory to run it against this checkout's build.
"""

import argparse
import math
import struct
import sys
import time

from panda3d import core

TASK = """#version 460
#extension GL_EXT_mesh_shader : require
layout(local_size_x = 32) in;
layout(std430) readonly buffer Bounds { vec4 bounds[]; };
layout(std430) buffer Stats { uint drawn; };
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform int num_meshlets;
uniform int cull;
struct Payload { uint ids[32]; };
taskPayloadSharedEXT Payload payload;
shared uint count;

bool in_frustum(vec4 sphere) {
  mat4 m = p3d_ModelViewProjectionMatrix;
  vec4 row0 = vec4(m[0][0], m[1][0], m[2][0], m[3][0]);
  vec4 row1 = vec4(m[0][1], m[1][1], m[2][1], m[3][1]);
  vec4 row2 = vec4(m[0][2], m[1][2], m[2][2], m[3][2]);
  vec4 row3 = vec4(m[0][3], m[1][3], m[2][3], m[3][3]);
  vec4 planes[6] = vec4[6](row3 + row0, row3 - row0, row3 + row1,
                           row3 - row1, row3 + row2, row3 - row2);
  for (int i = 0; i < 6; ++i) {
    if (dot(planes[i].xyz, sphere.xyz) + planes[i].w < -sphere.w * length(planes[i].xyz)) {
      return false;
    }
  }
  return true;
}

void main() {
  if (gl_LocalInvocationIndex == 0) {
    count = 0;
  }
  barrier();
  uint id = gl_GlobalInvocationID.x;
  if (id < uint(num_meshlets) && (cull == 0 || in_frustum(bounds[id]))) {
    payload.ids[atomicAdd(count, 1)] = id;
  }
  barrier();
  if (gl_LocalInvocationIndex == 0) {
    atomicAdd(drawn, count);
  }
  EmitMeshTasksEXT(count, 1, 1);
}
"""

MESH = """#version 460
#extension GL_EXT_mesh_shader : require
layout(local_size_x = 128) in;
layout(triangles, max_vertices = 81, max_primitives = 128) out;
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform int grid;
struct Payload { uint ids[32]; };
taskPayloadSharedEXT Payload payload;
layout(location = 0) out vec3 v_color[];

float height(vec2 p) {
  return 2.0 * sin(p.x * 0.11) * cos(p.y * 0.13) + 0.5 * sin(p.x * 0.5 + p.y * 0.3);
}

void main() {
  uint id = payload.ids[gl_WorkGroupID.x];
  vec2 origin = vec2(id % uint(grid), id / uint(grid)) * 8.0;
  SetMeshOutputsEXT(81, 128);

  uint i = gl_LocalInvocationIndex;
  if (i < 81u) {
    vec2 p = origin + vec2(i % 9u, i / 9u);
    float h = height(p);
    gl_MeshVerticesEXT[i].gl_Position = p3d_ModelViewProjectionMatrix * vec4(p, h, 1.0);
    // A tint per meshlet, so the meshlets show.
    float t = fract(sin(float(id) * 12.9898) * 43758.5453);
    vec3 ground = mix(vec3(0.15, 0.4, 0.15), vec3(0.85, 0.85, 0.8), clamp(h * 0.25 + 0.5, 0.0, 1.0));
    v_color[i] = ground * (0.75 + 0.25 * t);
  }

  uint q = i >> 1u;
  uint v0 = (q / 8u) * 9u + (q % 8u);
  gl_PrimitiveTriangleIndicesEXT[i] = (i & 1u) == 0u
    ? uvec3(v0, v0 + 1u, v0 + 10u)
    : uvec3(v0, v0 + 10u, v0 + 9u);
}
"""

FRAGMENT = """#version 460
layout(location = 0) in vec3 v_color;
layout(location = 0) out vec4 p3d_FragColor;
void main() {
  p3d_FragColor = vec4(v_color, 1.0);
}
"""


def make_terrain(grid: int) -> tuple[core.NodePath, core.ShaderBuffer]:
    """The terrain node, and the buffer its task shader counts meshlets in."""
    num = grid * grid
    radius = math.sqrt(4 * 4 + 4 * 4 + 2.5 * 2.5)
    bounds = bytearray()
    for i in range(num):
        x = (i % grid) * 8 + 4
        y = (i // grid) * 8 + 4
        bounds += struct.pack("4f", x, y, 0.0, radius)

    shader = core.Shader.make_mesh(core.Shader.SL_GLSL, MESH, FRAGMENT, TASK)
    if shader is None:
        sys.exit("the mesh shader did not compile")

    node = core.MeshDrawNode("terrain")
    node.add_draw((num + 31) // 32, 1, 1)
    # Bounds for Panda's own culling of the whole node.
    node.set_bounds(core.BoundingBox((0, 0, -3), (grid * 8, grid * 8, 3)))
    terrain = core.NodePath(node)
    terrain.set_shader(shader)
    terrain.set_shader_input("Bounds", core.ShaderBuffer("Bounds", bytes(bounds), core.Geom.UH_static))
    terrain.set_shader_input("grid", grid)
    terrain.set_shader_input("num_meshlets", num)
    stats = new_stats(terrain, cull=1)
    return terrain, stats


def new_stats(terrain: core.NodePath, cull: int) -> core.ShaderBuffer:
    """Set culling on or off, with a fresh zeroed counter."""
    stats = core.ShaderBuffer("Stats", 4, core.Geom.UH_dynamic)
    terrain.set_shader_input("Stats", stats)
    terrain.set_shader_input("cull", cull)
    return stats


def place_camera(cam: core.NodePath, grid: int) -> None:
    """Look across a corner of the terrain, so that much of it is out of view."""
    size = grid * 8
    cam.set_pos(size * 0.3, size * 0.15, 12)
    cam.look_at(size * 0.45, size * 0.45, 0)


def open_output(offscreen: bool, size: tuple[int, int]):
    pipe = core.GraphicsPipeSelection.get_global_ptr().make_module_pipe("p3vulkandisplay")
    if pipe is None or not pipe.is_valid():
        sys.exit("no Vulkan pipe")
    engine = core.GraphicsEngine.get_global_ptr()
    fbprops = core.FrameBufferProperties()
    fbprops.set_rgba_bits(8, 8, 8, 8)
    fbprops.set_depth_bits(24)
    flags = core.GraphicsPipe.BF_refuse_window if offscreen else core.GraphicsPipe.BF_require_window
    props = core.WindowProperties.size(*size)
    if not offscreen:
        props.set_title("Meshlets")
    output = engine.make_output(pipe, "meshlets", 0, fbprops, props, flags)
    if output is None:
        sys.exit("could not open an output")
    engine.open_windows()
    if not output.gsg.supports_mesh_shaders:
        sys.exit("this GSG has no mesh shaders")
    return engine, output


def setup_scene(output, grid: int):
    root = core.NodePath("root")
    terrain, stats = make_terrain(grid)
    terrain.reparent_to(root)
    lens = core.PerspectiveLens()
    lens.set_fov(70)
    lens.set_near_far(0.5, grid * 16)
    lens.set_aspect_ratio(output.get_x_size() / output.get_y_size())
    cam = root.attach_new_node(core.Camera("cam", lens))
    place_camera(cam, grid)
    region = output.make_display_region()
    region.camera = cam
    output.set_clear_color_active(True)
    output.set_clear_color((0.3, 0.45, 0.7, 1))
    return root, terrain, stats


def read_count(engine, output, stats: core.ShaderBuffer) -> int:
    data = engine.extract_shader_buffer_data(stats, output.gsg)
    return struct.unpack_from("I", bytes(data), 0)[0]


def check(grid: int) -> int:
    """Culled and unculled renders must match, and culling must skip meshlets."""
    engine, output = open_output(True, (640, 400))
    tex = core.Texture("result")
    output.add_render_texture(tex, core.GraphicsOutput.RTM_copy_ram)
    root, terrain, stats = setup_scene(output, grid)

    images = {}
    drawn = {}
    for cull in (0, 1):
        stats = new_stats(terrain, cull)
        engine.render_frame()
        engine.render_frame()
        image = core.PNMImage()
        tex.store(image)
        images[cull] = image
        # Two frames were drawn; the counter holds both.
        drawn[cull] = read_count(engine, output, stats) // 2

    differing = 0
    for y in range(images[0].get_y_size()):
        for x in range(images[0].get_x_size()):
            a = images[0].get_xel_val(x, y)
            b = images[1].get_xel_val(x, y)
            if max(abs(a[i] - b[i]) for i in range(3)) > 2:
                differing += 1
    total = grid * grid
    print(f"meshlets: {total}; drawn a frame without culling {drawn[0]}, with culling {drawn[1]}")
    print(f"pixels differing between the two: {differing}")
    ok = differing == 0 and drawn[0] == total and 0 < drawn[1] < total
    print("OK" if ok else "FAILED")
    engine.remove_all_windows()
    return 0 if ok else 1


def bench(grid: int, frames: int) -> int:
    engine, output = open_output(False, (1600, 1000))
    root, terrain, stats = setup_scene(output, grid)
    results: dict[int, list[float]] = {}
    for cull in (0, 1, 0, 1):
        new_stats(terrain, cull)
        for _ in range(30):
            engine.render_frame()
        start = time.perf_counter()
        for _ in range(frames):
            engine.render_frame()
        ms = (time.perf_counter() - start) * 1000 / frames
        results.setdefault(cull, []).append(ms)
    print(f"{grid}x{grid} meshlets, {grid * grid * 128} triangles, 1600x1000")
    for cull, times in results.items():
        label = "task-shader culling" if cull else "no culling"
        print(f"  {label}: {min(times):.2f} ms a frame")
    engine.remove_all_windows()
    return 0


def show(grid: int, seconds: float) -> int:
    engine, output = open_output(False, (1280, 800))
    setup_scene(output, grid)
    clock = core.ClockObject.get_global_clock()
    end = time.perf_counter() + seconds
    while output.is_valid() and time.perf_counter() < end:
        engine.render_frame()
        clock.tick()
    engine.remove_all_windows()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grid", type=int, default=128, help="meshlets across (default 128)")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--bench", type=int, metavar="FRAMES")
    parser.add_argument("--seconds", type=float, default=20.0, help="how long to show it")
    args = parser.parse_args()
    if args.check:
        return check(args.grid)
    if args.bench:
        return bench(args.grid, args.bench)
    return show(args.grid, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
