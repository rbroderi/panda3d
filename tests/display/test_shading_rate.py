from panda3d import core
import pytest

# A card over the whole buffer, each fragment writing its window position:
# at full rate every pixel differs from its neighbour, shaded once a 2x2
# block the pixels of a block are alike.
SIZE = 64
VERTEX = """#version 450
in vec4 p3d_Vertex;
uniform mat4 p3d_ModelViewProjectionMatrix;
void main() { gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex; }
"""
FRAGMENT = """#version 450
out vec4 color;
void main() { color = vec4(floor(gl_FragCoord.xy) / 64.0, 0.0, 1.0); }
"""
RATE_2X2 = 5  # (log2(2) << 2) | log2(2)


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
    gsg = buffer.gsg
    if not gsg.supports_fragment_shading_rate:
        engine.remove_window(buffer)
        pytest.skip("variable-rate shading not supported")

    yield engine, buffer
    engine.remove_window(buffer)


def rate_texture(gsg, rate_of):
    """A shading rate texture for the buffer, rate_of(column, row) each texel."""
    tw, th = gsg.fragment_shading_rate_texel_size
    w, h = -(-SIZE // tw), -(-SIZE // th)
    tex = core.Texture("rate")
    tex.setup_2d_texture(w, h, core.Texture.T_unsigned_byte, core.Texture.F_r8i)
    tex.set_ram_image(bytes(rate_of(x, y) for y in range(h) for x in range(w)))
    return tex


def render(engine, buffer, rate):
    root = core.NodePath("root")
    cm = core.CardMaker("card")
    cm.set_frame(-1, 1, -1, 1)
    card = root.attach_new_node(cm.generate())
    card.set_shader(core.Shader.make(core.Shader.SL_GLSL, VERTEX, FRAGMENT))
    lens = core.OrthographicLens()
    lens.set_film_size(2, 2)
    cam = root.attach_new_node(core.Camera("cam", lens))
    cam.set_pos(0, -5, 0)

    tex = core.Texture("result")
    buffer.add_render_texture(tex, core.GraphicsOutput.RTM_copy_ram)
    region = buffer.make_display_region()
    region.camera = cam
    if rate is not None:
        region.set_shading_rate_texture(rate)
    engine.render_frame()
    engine.render_frame()
    buffer.remove_display_region(region)
    buffer.clear_render_textures()
    image = core.PNMImage()
    assert tex.store(image)
    return image


def coarse(image, x, y):
    """Whether pixel (x, y), the corner of a 2x2 block, matches its neighbours."""
    a = image.get_xel(x, y)
    return a == image.get_xel(x + 1, y) and a == image.get_xel(x, y + 1)


def test_shading_rate_properties(vk_output):
    engine, buffer = vk_output
    gsg = buffer.gsg
    tw, th = gsg.fragment_shading_rate_texel_size
    assert tw >= 1 and th >= 1
    mw, mh = gsg.max_fragment_shading_rate
    assert mw >= 2 and mh >= 2


def test_full_rate(vk_output):
    engine, buffer = vk_output
    image = render(engine, buffer, None)
    assert not any(coarse(image, x, y) for x in range(0, SIZE - 1, 2) for y in range(0, SIZE - 1, 2))


def test_coarse_everywhere(vk_output):
    engine, buffer = vk_output
    image = render(engine, buffer, rate_texture(buffer.gsg, lambda x, y: RATE_2X2))
    assert all(coarse(image, x, y) for x in range(0, SIZE - 1, 2) for y in range(0, SIZE - 1, 2))


def test_coarse_half(vk_output):
    # Coarse on the right half only, then full rate again with none given.
    engine, buffer = vk_output
    tw, th = buffer.gsg.fragment_shading_rate_texel_size
    half = SIZE // tw // 2
    rate = rate_texture(buffer.gsg, lambda x, y: RATE_2X2 if x >= half else 0)
    image = render(engine, buffer, rate)
    for y in range(0, SIZE - 1, 2):
        for x in range(0, SIZE - 1, 2):
            assert coarse(image, x, y) == (x >= SIZE // 2)
    image = render(engine, buffer, None)
    assert not any(coarse(image, x, y) for x in range(0, SIZE - 1, 2) for y in range(0, SIZE - 1, 2))
