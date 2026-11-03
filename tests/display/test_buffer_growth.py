from panda3d import core
import pytest

# A Geom drawn, then grown in place and drawn again: its vertex and index
# buffers must grow with it.  The grown Geom is many empty quads and then one
# over the right half, so its last vertices and indices are far past the first
# buffers' ends; enough of them that the indices widen to 32 bits.
SIZE = 32
QUADS = 17000
VERTEX = """#version 450
in vec4 p3d_Vertex;
uniform mat4 p3d_ModelViewProjectionMatrix;
void main() { gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex; }
"""
FRAGMENT = """#version 450
out vec4 color;
void main() { color = vec4(1.0, 1.0, 1.0, 1.0); }
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

    yield engine, buffer
    engine.remove_window(buffer)


def add_quad(vertex, triangles, x0, x1):
    """Add a quad from x0 to x1, the whole height."""
    first = vertex.get_write_row()
    for x, z in ((x0, -1), (x1, -1), (x1, 1), (x0, 1)):
        vertex.add_data3(x, 0, z)
    triangles.add_vertices(first, first + 1, first + 2)
    triangles.add_vertices(first, first + 2, first + 3)


def render(engine, buffer, root, cam):
    tex = core.Texture("result")
    buffer.add_render_texture(tex, core.GraphicsOutput.RTM_copy_ram)
    region = buffer.make_display_region()
    region.camera = cam
    region.set_clear_color_active(True)
    region.set_clear_color((0, 0, 0, 1))
    engine.render_frame()
    engine.render_frame()
    buffer.remove_display_region(region)
    buffer.clear_render_textures()
    image = core.PNMImage()
    assert tex.store(image)
    return image


def lit(image, x):
    """Whether the middle row's pixel in column x is drawn."""
    return image.get_gray(x, SIZE // 2) > 0.5


@pytest.mark.parametrize("usage", [core.Geom.UH_static, core.Geom.UH_dynamic])
def test_grown_geom_is_drawn(vk_output, usage):
    engine, buffer = vk_output
    root = core.NodePath("root")
    data = core.GeomVertexData("quads", core.GeomVertexFormat.get_v3(), usage)
    triangles = core.GeomTriangles(usage)
    vertex = core.GeomVertexWriter(data, "vertex")
    add_quad(vertex, triangles, -1, 0)
    geom = core.Geom(data)
    geom.add_primitive(triangles)
    node = core.GeomNode("quads")
    node.add_geom(geom)
    quads = root.attach_new_node(node)
    quads.set_shader(core.Shader.make(core.Shader.SL_GLSL, VERTEX, FRAGMENT))
    quads.set_two_sided(True)
    lens = core.OrthographicLens()
    lens.set_film_size(2, 2)
    cam = root.attach_new_node(core.Camera("cam", lens))
    cam.set_pos(0, -5, 0)

    image = render(engine, buffer, root, cam)
    assert lit(image, SIZE // 4) and not lit(image, 3 * SIZE // 4)

    # In place, as a Geom rewritten each frame is: the same arrays, longer.
    vertex = core.GeomVertexWriter(data, "vertex")
    vertex.set_row(data.get_num_rows())
    for _ in range(QUADS):
        add_quad(vertex, triangles, 0.5, 0.5)
    add_quad(vertex, triangles, 0, 1)
    assert triangles.get_index_type() == core.Geom.NT_uint32

    image = render(engine, buffer, root, cam)
    assert lit(image, SIZE // 4) and lit(image, 3 * SIZE // 4)
