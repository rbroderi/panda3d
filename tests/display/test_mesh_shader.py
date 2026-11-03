from panda3d import core
import pytest
import struct

# A GRID x GRID grid of meshlets, one square cell each, in the XZ plane over
# 0..GRID, coloured from a storage buffer: (r, g, b, keep).  With the task
# stage, cells whose keep is 0 are culled before any mesh workgroup runs.
GRID = 4
SIZE = 64

TASK = """#version 460
#extension GL_EXT_mesh_shader : require
layout(local_size_x = 32) in;
layout(std430) readonly buffer Cells { vec4 cell_color[]; };
uniform int num_cells;
struct Payload { uint ids[32]; };
taskPayloadSharedEXT Payload payload;
shared uint count;
void main() {
  if (gl_LocalInvocationIndex == 0) {
    count = 0;
  }
  barrier();
  uint id = gl_GlobalInvocationID.x;
  if (id < uint(num_cells) && cell_color[id].a > 0.5) {
    payload.ids[atomicAdd(count, 1)] = id;
  }
  barrier();
  EmitMeshTasksEXT(count, 1, 1);
}
"""

MESH = """#version 460
#extension GL_EXT_mesh_shader : require
layout(local_size_x = 4) in;
layout(triangles, max_vertices = 4, max_primitives = 2) out;
layout(std430) readonly buffer Cells { vec4 cell_color[]; };
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform int grid;
#ifdef WITH_TASK
struct Payload { uint ids[32]; };
taskPayloadSharedEXT Payload payload;
#endif
layout(location = 0) out vec4 v_color[];
void main() {
#ifdef WITH_TASK
  uint id = payload.ids[gl_WorkGroupID.x];
#else
  uint id = gl_WorkGroupID.x;
#endif
  vec2 cell = vec2(id % uint(grid), id / uint(grid));
  SetMeshOutputsEXT(4, 2);
  uint i = gl_LocalInvocationIndex;
  vec2 c = cell + vec2(i & 1u, i >> 1u) * 0.8 + 0.1;
  gl_MeshVerticesEXT[i].gl_Position = p3d_ModelViewProjectionMatrix * vec4(c.x, 0.0, c.y, 1.0);
  v_color[i] = vec4(cell_color[id].rgb, 1.0);
  if (i == 0) {
    gl_PrimitiveTriangleIndicesEXT[0] = uvec3(0, 1, 2);
    gl_PrimitiveTriangleIndicesEXT[1] = uvec3(2, 1, 3);
  }
}
"""

FRAGMENT = """#version 460
layout(location = 0) in vec4 v_color;
layout(location = 0) out vec4 p3d_FragColor;
void main() {
  p3d_FragColor = v_color;
}
"""


@pytest.fixture(scope="module")
def vk_output(graphics_pipes):
    for pipe in graphics_pipes:
        if pipe.interface_name == 'Vulkan':
            break
    else:
        pytest.skip("no Vulkan pipe found")

    engine = core.GraphicsEngine()
    fbprops = core.FrameBufferProperties()
    fbprops.set_rgba_bits(8, 8, 8, 8)
    buffer = engine.make_output(pipe, 'buffer', 0, fbprops,
                                core.WindowProperties.size(SIZE, SIZE),
                                core.GraphicsPipe.BF_refuse_window)
    if buffer is None:
        pytest.skip("Vulkan pipe cannot make offscreen buffers")
    engine.open_windows()
    if not buffer.gsg.supports_mesh_shaders:
        engine.remove_window(buffer)
        pytest.skip("mesh shaders not supported")

    yield engine, buffer
    engine.remove_window(buffer)


def cell_colors():
    """Distinct colours per cell; every third cell is marked to be culled."""
    colors = []
    for i in range(GRID * GRID):
        keep = 0.0 if i % 3 == 2 else 1.0
        colors.append(((i % GRID + 1) / GRID, (i // GRID + 1) / GRID, 0.5, keep))
    return colors


def render(engine, buffer, shader, draws, colors):
    """Draw the grid; return the rendered image."""
    data = b"".join(struct.pack("4f", *c) for c in colors)
    cells = core.ShaderBuffer("Cells", data, core.Geom.UH_static)

    root = core.NodePath("root")
    node = core.MeshDrawNode("grid")
    for draw in draws:
        node.add_draw(draw)
    grid = root.attach_new_node(node)
    grid.set_shader(shader)
    grid.set_shader_input("Cells", cells)
    grid.set_shader_input("grid", GRID)
    grid.set_shader_input("num_cells", GRID * GRID)
    grid.set_two_sided(True)

    lens = core.OrthographicLens()
    lens.set_film_size(GRID, GRID)
    cam = root.attach_new_node(core.Camera("cam", lens))
    cam.set_pos(GRID / 2, -10, GRID / 2)

    tex = core.Texture("result")
    buffer.add_render_texture(tex, core.GraphicsOutput.RTM_copy_ram)
    buffer.set_clear_color_active(True)
    buffer.set_clear_color((0, 0, 0, 1))
    region = buffer.make_display_region()
    region.camera = cam
    engine.render_frame()
    engine.render_frame()
    buffer.remove_display_region(region)
    buffer.clear_render_textures()

    image = core.PNMImage()
    assert tex.store(image)
    return image


def cell_center(image, i):
    """The colour at the centre of cell i (as read back, row 0 is the bottom)."""
    x = int((i % GRID + 0.5) / GRID * image.get_x_size())
    y = int((i // GRID + 0.5) / GRID * image.get_y_size())
    return image.get_xel(x, y)


def test_mesh_shader_capabilities(vk_output):
    engine, buffer = vk_output
    assert buffer.gsg.supported_shader_capabilities & core.Shader.C_mesh_shader
    shader = core.Shader.make_mesh(core.Shader.SL_GLSL, MESH, FRAGMENT)
    assert shader is not None
    assert shader.has_stage(core.Shader.Stage.MESH)
    assert shader.has_stage(core.Shader.Stage.FRAGMENT)
    assert not shader.has_stage(core.Shader.Stage.VERTEX)
    assert shader.get_used_capabilities() & core.Shader.C_mesh_shader


def test_mesh_shader_grid(vk_output):
    engine, buffer = vk_output
    shader = core.Shader.make_mesh(core.Shader.SL_GLSL, MESH, FRAGMENT)
    colors = cell_colors()
    image = render(engine, buffer, shader, [(GRID * GRID, 1, 1)], colors)
    for i, (r, g, b, keep) in enumerate(colors):
        assert tuple(cell_center(image, i)) == pytest.approx((r, g, b), abs=0.02)


def test_mesh_shader_split_draws(vk_output):
    # Two draws of the first half of the grid: cells past it stay cleared.
    engine, buffer = vk_output
    shader = core.Shader.make_mesh(core.Shader.SL_GLSL, MESH, FRAGMENT)
    colors = cell_colors()
    half = GRID * GRID // 2
    image = render(engine, buffer, shader, [(half, 1, 1), (half, 1, 1)], colors)
    for i, (r, g, b, keep) in enumerate(colors):
        expected = (r, g, b) if i < half else (0, 0, 0)
        assert tuple(cell_center(image, i)) == pytest.approx(expected, abs=0.02)


def test_task_shader_culls(vk_output):
    engine, buffer = vk_output
    mesh = MESH.replace("#version 460\n", "#version 460\n#define WITH_TASK 1\n")
    shader = core.Shader.make_mesh(core.Shader.SL_GLSL, mesh, FRAGMENT, TASK)
    assert shader is not None
    assert shader.has_stage(core.Shader.Stage.TASK)
    colors = cell_colors()
    image = render(engine, buffer, shader, [(1, 1, 1)], colors)
    for i, (r, g, b, keep) in enumerate(colors):
        expected = (r, g, b) if keep else (0, 0, 0)
        assert tuple(cell_center(image, i)) == pytest.approx(expected, abs=0.02)


def test_mesh_and_vertex_stages_do_not_mix():
    vertex = core.Shader.make(core.Shader.SL_GLSL, """#version 460
in vec4 p3d_Vertex;
uniform mat4 p3d_ModelViewProjectionMatrix;
layout(location = 0) out vec4 v_color;
void main() { gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex; v_color = vec4(1.0); }
""", FRAGMENT)
    assert vertex is not None
    mesh = core.Shader.make_mesh(core.Shader.SL_GLSL, MESH, FRAGMENT)
    assert mesh is not None
    assert not vertex.add_module(mesh.modify_module(core.Shader.Stage.MESH))
