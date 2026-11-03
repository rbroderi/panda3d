from panda3d import core
import pytest
import struct

# Each invocation samples entry i of the table (wrapping round its size) and
# writes what it read.
COUNT = 8
SHADER = """#version 460
#extension GL_EXT_nonuniform_qualifier : require
layout(local_size_x = 8) in;
uniform sampler2D textures[];
uniform int num_textures;
layout(rgba32f) uniform writeonly image2D result;
void main() {
  int i = int(gl_GlobalInvocationID.x);
  vec4 color = textureLod(textures[nonuniformEXT(i % num_textures)], vec2(0.5), 0.0);
  imageStore(result, ivec2(i, 0), color);
}
"""


@pytest.fixture(scope="module")
def vk_gsg(graphics_pipes):
    for pipe in graphics_pipes:
        if pipe.interface_name == 'Vulkan':
            break
    else:
        pytest.skip("no Vulkan pipe found")

    engine = core.GraphicsEngine()
    fbprops = core.FrameBufferProperties()
    fbprops.set_rgba_bits(8, 8, 8, 8)
    buffer = engine.make_output(pipe, 'buffer', 0, fbprops,
                                core.WindowProperties.size(16, 16),
                                core.GraphicsPipe.BF_refuse_window)
    if buffer is None:
        pytest.skip("Vulkan pipe cannot make offscreen buffers")
    engine.open_windows()
    gsg = buffer.gsg
    if not gsg.supports_texture_tables:
        engine.remove_window(buffer)
        pytest.skip("texture tables not supported")

    yield gsg
    engine.remove_window(buffer)


def solid(r, g, b):
    """A 1x1 texture of one colour."""
    tex = core.Texture("solid")
    tex.setup_2d_texture(1, 1, core.Texture.T_unsigned_byte, core.Texture.F_rgba8)
    tex.set_ram_image(bytes((int(b * 255), int(g * 255), int(r * 255), 255)))
    return tex


def colors(n):
    return [((i + 1) / (n + 1), 1 - i / n, (i % 2) * 1.0) for i in range(n)]


def sample(gsg, table, num):
    """Run the shader over COUNT entries of table; return what each read."""
    result = core.Texture("result")
    result.setup_2d_texture(COUNT, 1, core.Texture.T_float, core.Texture.F_rgba32)
    shader = core.Shader.make_compute(core.Shader.SL_GLSL, SHADER)
    assert shader is not None
    attrib = core.ShaderAttrib.make(shader)
    attrib = attrib.set_shader_input("textures", table)
    attrib = attrib.set_shader_input("num_textures", num)
    attrib = attrib.set_shader_input("result", result)
    engine = gsg.get_engine()
    engine.dispatch_compute((1, 1, 1), attrib, gsg)
    assert engine.extract_texture_data(result, gsg)
    data = result.get_ram_image()
    return [struct.unpack_from("4f", data, i * 16) for i in range(COUNT)]


def check(read, expected, num):
    for i, texel in enumerate(read):
        r, g, b = expected[i % num]
        # Red and blue may come back either way round.
        assert sorted((texel[0], texel[2])) == pytest.approx(sorted((r, b)), abs=0.01)
        assert texel[1] == pytest.approx(g, abs=0.01)


def test_texture_table_capabilities(vk_gsg):
    assert vk_gsg.supported_shader_capabilities & core.Shader.C_texture_table
    assert vk_gsg.max_texture_table_size >= COUNT
    shader = core.Shader.make_compute(core.Shader.SL_GLSL, SHADER)
    assert shader.get_used_capabilities() & core.Shader.C_texture_table


def test_texture_table_sample(vk_gsg):
    table = core.TextureTable("materials")
    expected = colors(5)
    for rgb in expected:
        table.add_texture(solid(*rgb))
    assert table.get_num_textures() == 5
    check(sample(vk_gsg, table, 5), expected, 5)


def test_texture_table_grows_and_changes(vk_gsg):
    table = core.TextureTable("materials")
    expected = colors(COUNT)
    for rgb in expected[:3]:
        table.add_texture(solid(*rgb))
    check(sample(vk_gsg, table, 3), expected[:3], 3)

    # Added: written into the set in use, where update-after-bind allows.
    for rgb in expected[3:]:
        table.add_texture(solid(*rgb))
    check(sample(vk_gsg, table, COUNT), expected, COUNT)

    # Replaced: a new set.
    expected[2] = (0.2, 0.4, 0.6)
    table.set_texture(2, solid(*expected[2]))
    assert table.find_texture(table.get_texture(2)) == 2
    check(sample(vk_gsg, table, COUNT), expected, COUNT)

    # Grown past its room (16): a new, bigger set.
    for i in range(20):
        table.add_texture(solid(0.5, 0.5, 0.5))
    check(sample(vk_gsg, table, COUNT), expected, COUNT)


def test_texture_table_sampler(vk_gsg):
    # A 2x1 texture, red then green, sampled at its middle: nearest picks one
    # texel, linear blends the two.
    tex = core.Texture("two")
    tex.setup_2d_texture(2, 1, core.Texture.T_unsigned_byte, core.Texture.F_rgba8)
    tex.set_ram_image(bytes((0, 0, 255, 255, 0, 255, 0, 255)))
    nearest = core.SamplerState()
    nearest.set_minfilter(core.SamplerState.FT_nearest)
    nearest.set_magfilter(core.SamplerState.FT_nearest)
    linear = core.SamplerState()
    linear.set_minfilter(core.SamplerState.FT_linear)
    linear.set_magfilter(core.SamplerState.FT_linear)
    table = core.TextureTable("sampled")
    table.add_texture(tex, nearest)
    table.add_texture(tex, linear)
    read = sample(vk_gsg, table, 2)
    assert max(read[0][0], read[0][2]) + read[0][1] == pytest.approx(1.0, abs=0.01)
    assert read[0][1] in (pytest.approx(0.0, abs=0.01), pytest.approx(1.0, abs=0.01))
    assert read[1][1] == pytest.approx(0.5, abs=0.02)
