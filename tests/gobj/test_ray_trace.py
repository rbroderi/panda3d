from panda3d import core
import pytest


def make_quad(strip=False, animated=False):
    """A unit square in the XY plane, as triangles or as a strip."""
    vformat = core.GeomVertexFormat.get_v3()
    if animated:
        array = core.GeomVertexArrayFormat()
        array.add_column("vertex", 3, core.Geom.NT_float32, core.Geom.C_point)
        array.add_column("transform_blend", 1, core.Geom.NT_uint16, core.Geom.C_index)
        aformat = core.GeomVertexFormat()
        aformat.add_array(array)
        anim = core.GeomVertexAnimationSpec()
        anim.set_panda()
        aformat.set_animation(anim)
        vformat = core.GeomVertexFormat.register_format(aformat)

    vdata = core.GeomVertexData("quad", vformat, core.Geom.UH_static)
    vdata.unclean_set_num_rows(4)
    vertex = core.GeomVertexWriter(vdata, "vertex")
    for x, y in ((0, 0), (1, 0), (1, 1), (0, 1)):
        vertex.set_data3(x, y, 0)

    if animated:
        transform = core.UserVertexTransform("move")
        table = core.TransformBlendTable()
        table.add_blend(core.TransformBlend(transform, 1.0))
        vdata.set_transform_blend_table(table)
        blend = core.GeomVertexWriter(vdata, "transform_blend")
        for _ in range(4):
            blend.set_data1i(0)

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


def test_ray_trace_mesh_empty():
    mesh = core.RayTraceMesh("empty")
    assert mesh.name == "empty"
    assert mesh.num_geoms == 0
    assert mesh.num_triangles == 0
    assert mesh.num_vertices == 0
    assert not mesh.animated
    assert not mesh.update_animation()


@pytest.fixture
def reference_geoms():
    page = core.load_prc_file_data("", "ray-trace-reference-geoms true")
    yield
    core.unload_prc_file(page)


def test_ray_trace_mesh_copies_plain_triangles_if_asked():
    page = core.load_prc_file_data("", "ray-trace-reference-geoms false")
    try:
        mesh = core.RayTraceMesh()
        mesh.add_geom(make_quad())
        assert mesh.num_triangles == 2
        assert mesh.num_referenced_geoms == 0
    finally:
        core.unload_prc_file(page)


def test_ray_trace_mesh_references_plain_triangles(reference_geoms):
    mesh = core.RayTraceMesh()
    assert mesh.add_geom(make_quad()) == 0
    assert mesh.num_geoms == 1
    assert mesh.num_triangles == 2
    assert mesh.num_vertices == 4
    assert mesh.num_referenced_geoms == 1
    assert not mesh.animated


def test_ray_trace_mesh_copies_strips(reference_geoms):
    mesh = core.RayTraceMesh()
    assert mesh.add_geom(make_quad(strip=True)) == 0
    assert mesh.num_triangles == 2
    assert mesh.num_referenced_geoms == 0


def test_ray_trace_mesh_poses_animated(reference_geoms):
    mesh = core.RayTraceMesh()
    mesh.add_geom(make_quad(animated=True))
    assert mesh.animated
    assert mesh.num_referenced_geoms == 0
    assert mesh.update_animation()


def test_ray_trace_mesh_skips_geom_without_vertices():
    vformat = core.GeomVertexFormat.register_format(core.GeomVertexArrayFormat(
        "normal", 3, core.Geom.NT_float32, core.Geom.C_normal))
    vdata = core.GeomVertexData("normals", vformat, core.Geom.UH_static)
    geom = core.Geom(vdata)
    mesh = core.RayTraceMesh()
    assert mesh.add_geom(geom) == -1
    assert mesh.num_geoms == 0


def test_ray_trace_mesh_clear(reference_geoms):
    mesh = core.RayTraceMesh()
    mesh.add_geom(make_quad())
    mesh.add_geom(make_quad(strip=True))
    assert mesh.num_triangles == 4
    mesh.clear()
    assert mesh.num_geoms == 0
    assert mesh.num_triangles == 0
    assert mesh.num_referenced_geoms == 0


def test_ray_trace_scene_instances():
    mesh = core.RayTraceMesh()
    mesh.add_geom(make_quad())
    scene = core.RayTraceScene("scene")
    assert isinstance(scene, core.ShaderBuffer)
    assert scene.num_instances == 0

    mat = core.LMatrix4.translate_mat(1, 2, 3)
    assert scene.add_instance(mesh, mat, 0x0f, 7) == 0
    assert scene.add_instance(mesh) == 1
    assert scene.num_instances == 2
    assert scene.get_instance_mesh(0) == mesh
    assert scene.get_instance_transform(0).almost_equal(mat)

    scene.set_instance_transform(1, mat)
    assert scene.get_instance_transform(1).almost_equal(mat)

    other = core.RayTraceMesh()
    scene.set_instance_mesh(1, other)
    assert scene.get_instance_mesh(1) == other

    scene.clear_instances()
    assert scene.num_instances == 0


def test_ray_trace_scene_custom_index_range():
    mesh = core.RayTraceMesh()
    scene = core.RayTraceScene()
    with pytest.raises(AssertionError):
        scene.add_instance(mesh, core.LMatrix4.ident_mat(), 0xff, 1 << 24)


def test_shader_type_acceleration_structure():
    stype = core.ShaderType.ACCELERATION_STRUCTURE
    assert stype is not None
    assert str(stype) == "accelerationStructure"
