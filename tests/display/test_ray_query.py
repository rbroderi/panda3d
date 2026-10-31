from panda3d import core
import pytest
import struct

# A ray straight down (-z) from each texel of a SIZE x SIZE grid over -1..1,
# writing (geometry index, t, geometry index, custom index of the instance
# hit), or (-1, -1, -1, -1) if it hits nothing.  The geometry index is in both
# red and blue, so the result reads the same whichever of the two comes first.
SIZE = 8
RAY_QUERY_SHADER = """#version 460
#extension GL_EXT_ray_query : require
layout(local_size_x = 8, local_size_y = 8) in;
uniform accelerationStructureEXT scene;
layout(rgba32f) uniform writeonly image2D hits;
void main() {
  ivec2 at = ivec2(gl_GlobalInvocationID.xy);
  vec2 xy = (vec2(at) + 0.5) / 8.0 * 2.0 - 1.0;
  rayQueryEXT q;
  rayQueryInitializeEXT(q, scene, gl_RayFlagsOpaqueEXT, 0xFF,
                        vec3(xy, 10.0), 0.0, vec3(0.0, 0.0, -1.0), 100.0);
  while (rayQueryProceedEXT(q)) {}
  vec4 result = vec4(-1.0, -1.0, -1.0, -1.0);
  if (rayQueryGetIntersectionTypeEXT(q, true) != gl_RayQueryCommittedIntersectionNoneEXT) {
    float geometry = float(rayQueryGetIntersectionGeometryIndexEXT(q, true));
    result = vec4(geometry, rayQueryGetIntersectionTEXT(q, true), geometry,
                  float(rayQueryGetIntersectionInstanceCustomIndexEXT(q, true)));
  }
  imageStore(hits, at, result);
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
    if not gsg.supports_ray_query:
        engine.remove_window(buffer)
        pytest.skip("ray queries not supported")

    yield gsg
    engine.remove_window(buffer)


@pytest.fixture
def reference_geoms():
    page = core.load_prc_file_data("", "ray-trace-reference-geoms true")
    yield
    core.unload_prc_file(page)


def make_quad(z, strip=False):
    """A 2x2 square over -1..1 at height z, as triangles or as a strip."""
    vdata = core.GeomVertexData("quad", core.GeomVertexFormat.get_v3(), core.Geom.UH_static)
    vdata.unclean_set_num_rows(4)
    vertex = core.GeomVertexWriter(vdata, "vertex")
    for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        vertex.set_data3(x, y, z)
    if strip:
        prim = core.GeomTristrips(core.Geom.UH_static)
        prim.add_vertices(0, 1, 3, 2)
        prim.close_primitive()
    else:
        prim = core.GeomTriangles(core.Geom.UH_static)
        prim.add_vertices(0, 1, 2)
        prim.add_vertices(0, 2, 3)
    geom = core.Geom(vdata)
    geom.add_primitive(prim)
    return geom


def trace(gsg, scene):
    """Cast the grid of rays at the scene; return the (t, custom, geometry) hits."""
    hits = core.Texture("hits")
    hits.setup_2d_texture(SIZE, SIZE, core.Texture.T_float, core.Texture.F_rgba32)
    shader = core.Shader.make_compute(core.Shader.SL_GLSL, RAY_QUERY_SHADER)
    assert shader is not None
    attrib = core.ShaderAttrib.make(shader)
    attrib = attrib.set_shader_input("scene", scene)
    attrib = attrib.set_shader_input("hits", hits)
    engine = gsg.get_engine()
    engine.dispatch_compute((1, 1, 1), attrib, gsg)
    assert engine.extract_texture_data(hits, gsg)
    data = hits.get_ram_image()
    texels = [struct.unpack_from("4f", data, i * 16) for i in range(SIZE * SIZE)]
    return [(t, custom, geometry) for geometry, t, _, custom in texels]


def test_ray_query_capabilities(vk_gsg):
    caps = vk_gsg.supported_shader_capabilities
    assert caps & core.Shader.C_ray_query
    shader = core.Shader.make_compute(core.Shader.SL_GLSL, RAY_QUERY_SHADER)
    assert shader.get_used_capabilities() & core.Shader.C_ray_query


def test_ray_query_hits(vk_gsg):
    mesh = core.RayTraceMesh("quad")
    mesh.add_geom(make_quad(0))
    scene = core.RayTraceScene("scene")
    scene.add_instance(mesh, core.LMatrix4.ident_mat(), 0xff, 5)
    for t, custom, geometry in trace(vk_gsg, scene):
        assert t == pytest.approx(10.0)
        assert custom == 5
        assert geometry == 0


def test_ray_query_empty_scene_misses(vk_gsg):
    scene = core.RayTraceScene("empty")
    for t, custom, geometry in trace(vk_gsg, scene):
        assert t == -1


def test_ray_query_instance_moved(vk_gsg):
    mesh = core.RayTraceMesh("quad")
    mesh.add_geom(make_quad(0))
    scene = core.RayTraceScene("scene")
    scene.add_instance(mesh)
    assert trace(vk_gsg, scene)[0][0] == pytest.approx(10.0)

    # Only moved: the structure is refitted.
    scene.set_instance_transform(0, core.LMatrix4.translate_mat(0, 0, 4))
    assert trace(vk_gsg, scene)[0][0] == pytest.approx(6.0)

    # Hidden by its mask.
    scene.set_instance_mask(0, 0)
    assert trace(vk_gsg, scene)[0][0] == -1


def test_ray_query_closest_instance(vk_gsg):
    mesh = core.RayTraceMesh("quad")
    mesh.add_geom(make_quad(0))
    scene = core.RayTraceScene("scene")
    scene.add_instance(mesh, core.LMatrix4.translate_mat(0, 0, 1), 0xff, 1)
    scene.add_instance(mesh, core.LMatrix4.translate_mat(0, 0, 3), 0xff, 2)
    for t, custom, geometry in trace(vk_gsg, scene):
        assert t == pytest.approx(7.0)
        assert custom == 2


def test_ray_query_referenced_and_copied(vk_gsg, reference_geoms):
    # Plain triangles are built from the Geom's own buffers, strips copied;
    # both must be hit the same, each its own geometry.
    mesh = core.RayTraceMesh("two")
    mesh.add_geom(make_quad(0))
    mesh.add_geom(make_quad(2, strip=True))
    assert mesh.num_referenced_geoms == 1
    scene = core.RayTraceScene("scene")
    scene.add_instance(mesh)
    for t, custom, geometry in trace(vk_gsg, scene):
        assert t == pytest.approx(8.0)
        assert geometry == 1


def test_ray_query_referenced_empty_primitive(vk_gsg, reference_geoms):
    # An empty primitive beside the quad's adds nothing (and has no index
    # buffer to build from).
    geom = make_quad(0)
    geom.add_primitive(core.GeomTriangles(core.Geom.UH_static))
    mesh = core.RayTraceMesh("quad")
    mesh.add_geom(geom)
    assert mesh.num_referenced_geoms == 1
    scene = core.RayTraceScene("scene")
    scene.add_instance(mesh)
    for t, custom, geometry in trace(vk_gsg, scene):
        assert t == pytest.approx(10.0)


def test_ray_query_mesh_changed(vk_gsg):
    mesh = core.RayTraceMesh("quad")
    mesh.add_geom(make_quad(0))
    scene = core.RayTraceScene("scene")
    scene.add_instance(mesh)
    assert trace(vk_gsg, scene)[0][0] == pytest.approx(10.0)

    mesh.clear()
    mesh.add_geom(make_quad(5), core.LMatrix4.translate_mat(0, 0, -1))
    assert trace(vk_gsg, scene)[0][0] == pytest.approx(6.0)
