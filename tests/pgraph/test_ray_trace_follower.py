from panda3d import core
import pytest


def make_scene(count):
    """A scene of count instances of one (empty) mesh."""
    mesh = core.RayTraceMesh("mesh")
    scene = core.RayTraceScene("scene")
    for _ in range(count):
        scene.add_instance(mesh)
    return scene


def test_ray_trace_follower_still():
    scene = make_scene(1)
    root = core.NodePath("root")
    node = root.attach_new_node("node")
    follower = core.RayTraceFollower(scene, root)
    follower.add_instance(0, node)
    assert follower.num_instances == 1
    assert follower.scene == scene
    assert follower.update() == 0


def test_ray_trace_follower_moves():
    root = core.NodePath("root")
    node = root.attach_new_node("node")
    node.set_pos(1, 2, 3)
    scene = make_scene(1)
    scene.set_instance_transform(0, node.get_mat(root))
    follower = core.RayTraceFollower(scene, root)
    follower.add_instance(0, node)

    node.set_pos(4, 5, 6)
    assert follower.update() == 1
    assert scene.get_instance_transform(0) == node.get_mat(root)
    assert follower.update() == 0

    # Set again where it is: a new TransformState maybe, but not moved.
    node.set_pos(4, 5, 6)
    assert follower.update() == 0


def test_ray_trace_follower_parent_moves():
    root = core.NodePath("root")
    parent = root.attach_new_node("parent")
    child = parent.attach_new_node("child")
    child.set_pos(0, 0, 1)
    scene = make_scene(1)
    scene.set_instance_transform(0, child.get_mat(root))
    follower = core.RayTraceFollower(scene, root)
    follower.add_instance(0, child)

    parent.set_hpr(90, 0, 0)
    parent.set_pos(3, 0, 0)
    assert follower.update() == 1
    assert scene.get_instance_transform(0).almost_equal(child.get_mat(root))


def test_ray_trace_follower_relative_to_moves():
    top = core.NodePath("top")
    world = top.attach_new_node("world")
    node = top.attach_new_node("node")
    scene = make_scene(1)
    follower = core.RayTraceFollower(scene, world)
    follower.add_instance(0, node)
    assert follower.update() == 0

    # The node stays put, but the space the instances are placed in moves.
    world.set_pos(0, 0, 2)
    assert follower.update() == 1
    assert scene.get_instance_transform(0) == core.LMatrix4.translate_mat(0, 0, -2)


def test_ray_trace_follower_shared_node():
    root = core.NodePath("root")
    a = root.attach_new_node("a")
    b = root.attach_new_node("b")
    scene = make_scene(3)
    follower = core.RayTraceFollower(scene, root)
    # Two instances (a GeomNode's two Geoms, say) follow one node.
    follower.add_instance(0, a)
    follower.add_instance(1, a)
    follower.add_instance(2, b)

    a.set_x(1)
    assert follower.update() == 2
    assert scene.get_instance_transform(0) == a.get_mat(root)
    assert scene.get_instance_transform(1) == a.get_mat(root)
    assert scene.get_instance_transform(2) == core.LMatrix4.ident_mat()


def test_ray_trace_follower_clear():
    root = core.NodePath("root")
    node = root.attach_new_node("node")
    scene = make_scene(1)
    follower = core.RayTraceFollower(scene, root)
    follower.add_instance(0, node)
    follower.clear()
    assert follower.num_instances == 0
    node.set_x(1)
    assert follower.update() == 0
    assert scene.get_instance_transform(0) == core.LMatrix4.ident_mat()


def test_ray_trace_follower_no_relative_to():
    top = core.NodePath("top")
    node = top.attach_new_node("node")
    scene = make_scene(1)
    follower = core.RayTraceFollower(scene)
    follower.add_instance(0, node)
    node.set_z(5)
    assert follower.update() == 1
    assert scene.get_instance_transform(0) == core.LMatrix4.translate_mat(0, 0, 5)


def test_ray_trace_follower_bad_instance():
    scene = make_scene(1)
    follower = core.RayTraceFollower(scene)
    with pytest.raises(AssertionError):
        follower.add_instance(1, core.NodePath("node"))
