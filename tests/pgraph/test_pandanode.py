from panda3d.core import PandaNode, TransformState
from contextlib import contextmanager
import pytest
import gc


@contextmanager
def gc_disabled():
    gc.disable()
    gc.collect()
    gc.freeze()
    gc.set_debug(gc.DEBUG_SAVEALL)
    gc.garbage.clear()

    try:
        yield
    finally:
        gc.set_debug(0)
        gc.garbage.clear()
        gc.unfreeze()
        gc.collect()
        gc.enable()


def test_node_prev_transform():
    identity = TransformState.make_identity()
    t1 = TransformState.make_pos((1, 0, 0))
    t2 = TransformState.make_pos((2, 0, 0))
    t3 = TransformState.make_pos((3, 0, 0))

    node = PandaNode("node")
    assert node.transform == identity
    assert node.prev_transform == identity
    assert not node.has_dirty_prev_transform()

    node.transform = t1
    assert node.transform == t1
    assert node.prev_transform == identity
    assert node.has_dirty_prev_transform()

    node.transform = t2
    assert node.transform == t2
    assert node.prev_transform == identity
    assert node.has_dirty_prev_transform()

    node.reset_prev_transform()
    assert node.transform == t2
    assert node.prev_transform == t2
    assert not node.has_dirty_prev_transform()

    node.transform = t3
    assert node.prev_transform == t2
    assert node.has_dirty_prev_transform()
    PandaNode.reset_all_prev_transform()
    assert node.transform == t3
    assert node.prev_transform == t3
    assert not node.has_dirty_prev_transform()


def test_node_tag_cycle():
    with gc_disabled():
        node = PandaNode('test_node_tag_cycle')
        node.set_python_tag('self', node)
        node.set_python_tag('self2', node)
        assert gc.is_tracked(node)
        node = None

        gc.collect()
        assert len(gc.garbage) > 0

        for g in gc.garbage:
            if isinstance(g, PandaNode) and g.name == 'test_node_tag_cycle':
                break
        else:
            assert False


def other_wrapper(node):
    # Returns another wrapper for the same node, by temporarily attaching a
    # child.
    child = PandaNode('child')
    node.add_child(child)
    node2 = child.get_parent(0)
    node.remove_child(0)
    assert node2 is not node
    assert node2.this == node.this
    return node2


def in_garbage(name):
    return any(isinstance(g, PandaNode) and g.name == name for g in gc.garbage)


def test_node_tag_cycle_multiple_wrappers():
    with gc_disabled():
        node = PandaNode('test_node_tag_cycle_multiple_wrappers')
        node.set_python_tag('self', node)

        # Find another reference to the same node, we do this by temporarily
        # attaching a child.
        child = PandaNode('child')
        node.add_child(child)
        node2 = child.get_parent(0)
        node.remove_child(0)
        child = None

        assert node2 == node
        assert node2 is not node
        assert node2.this == node.this

        node.set_python_tag('self2', node2)

        node = None
        node2 = None

        gc.collect()
        assert len(gc.garbage) > 0

        for g in gc.garbage:
            if isinstance(g, PandaNode) and g.name == 'test_node_tag_cycle_multiple_wrappers':
                break
        else:
            pytest.fail('not found in garbage')


def test_node_tag_cycle_wrapper_removed():
    # A second wrapper goes away before the cycle is collected.
    with gc_disabled():
        node = PandaNode('test_node_tag_cycle_wrapper_removed')
        node2 = other_wrapper(node)
        node.set_python_tag('self', node)
        node2 = None

        node = None
        gc.collect()
        assert in_garbage('test_node_tag_cycle_wrapper_removed')


def test_node_tag_cycle_one_wrapper_left():
    # Two wrappers are in the cycle; one of them is let go first.
    with gc_disabled():
        node = PandaNode('test_node_tag_cycle_one_wrapper_left')
        node2 = other_wrapper(node)
        node.set_python_tag('self', node)
        node.set_python_tag('self2', node2)
        node.clear_python_tag('self2')
        node2 = None

        node = None
        gc.collect()
        assert in_garbage('test_node_tag_cycle_one_wrapper_left')


def test_node_tag_cycle_other_wrapper_alive():
    # The cycle only goes through one wrapper, but another one is still
    # reachable, so the tags must survive a real collection.
    gc.collect()
    node = PandaNode('test_node_tag_cycle_other_wrapper_alive')
    node2 = other_wrapper(node)
    node.set_python_tag('self', node)
    node = None

    gc.collect()
    assert node2.get_python_tag('self') is not None
    assert node2.get_python_tag('self').this == node2.this
    node2.clear_python_tag('self')


@pytest.mark.parametrize("num_wrappers", [1, 2])
def test_node_tag_cycle_held_by_parent(num_wrappers):
    # The node is also held by C++ (a parent), so its tags must survive.
    gc.collect()
    parent = PandaNode('parent')
    node = PandaNode('test_node_tag_cycle_held_by_parent')
    parent.add_child(node)
    node.set_python_tag('self', node)
    if num_wrappers > 1:
        node.set_python_tag('self2', other_wrapper(node))
    node = None

    gc.collect()
    child = parent.get_child(0)
    assert child.get_python_tag('self') is not None
    assert child.get_python_tag('self').this == child.this
    if num_wrappers > 1:
        assert child.get_python_tag('self2').this == child.this

    parent.remove_all_children()


def test_node_tag_cycle_held_by_node_path():
    # The node is held by a NodePath, which is held in C++.
    from panda3d.core import NodePath, NodePathCollection

    gc.collect()
    paths = NodePathCollection()
    node = PandaNode('test_node_tag_cycle_held_by_node_path')
    paths.add_path(NodePath(node))
    node.set_python_tag('self', node)
    node.set_python_tag('self2', other_wrapper(node))
    node = None

    gc.collect()
    node = paths.get_path(0).node()
    assert node.get_python_tag('self').this == node.this
    assert node.get_python_tag('self2').this == node.this
    node.clear_python_tag('self')
    node.clear_python_tag('self2')


def test_node_tag_cycle_shared_tags():
    # A copy shares the tags until either node changes them, so the tags
    # can't be collected while the copy is alive.
    gc.collect()
    node = PandaNode('test_node_tag_cycle_shared_tags')
    node.set_python_tag('self', node)
    copy = node.make_copy()
    node = None

    gc.collect()
    assert copy.get_python_tag('self') is not None
    assert copy.get_python_tag('self').name == 'test_node_tag_cycle_shared_tags'
    copy.clear_python_tag('self')


@pytest.mark.parametrize("cls_name", ["GeomNode", "ModelNode", "CollisionNode"])
@pytest.mark.parametrize("num_wrappers", [1, 2])
def test_node_tag_cycle_subclass(cls_name, num_wrappers):
    # C++ subclasses of PandaNode take part in garbage collection too.
    import panda3d.core
    cls = getattr(panda3d.core, cls_name)

    with gc_disabled():
        node = cls('test_node_tag_cycle_subclass')
        assert gc.is_tracked(node)
        node.set_python_tag('self', node)
        if num_wrappers > 1:
            node.set_python_tag('self2', other_wrapper(node))
        node = None

        gc.collect()
        assert in_garbage('test_node_tag_cycle_subclass')


def test_node_tag_cycle_subclass_held_by_parent():
    from panda3d.core import GeomNode

    gc.collect()
    parent = PandaNode('parent')
    node = GeomNode('test_node_tag_cycle_subclass_held_by_parent')
    parent.add_child(node)
    node.set_python_tag('self', node)
    node = None

    gc.collect()
    child = parent.get_child(0)
    assert child.get_python_tag('self').this == child.this
    parent.remove_all_children()


def test_node_path_tag_cycle():
    from panda3d.core import NodePath

    with gc_disabled():
        path = NodePath('test_node_path_tag_cycle')
        assert gc.is_tracked(path)
        path.set_python_tag('self', path)
        path = None

        gc.collect()
        assert any(isinstance(g, NodePath) and g.name == 'test_node_path_tag_cycle'
                   for g in gc.garbage)


def test_node_path_tag_cycle_held():
    # Another NodePath to the same node, or a parent, keeps the tags alive.
    from panda3d.core import NodePath

    gc.collect()
    path = NodePath('test_node_path_tag_cycle_held')
    path.set_python_tag('self', path)
    other = NodePath(path)
    path = None

    root = NodePath('root')
    child = root.attach_new_node('child')
    child.set_python_tag('self', child)
    child = None

    gc.collect()
    assert other.get_python_tag('self').name == 'test_node_path_tag_cycle_held'
    assert root.get_child(0).get_python_tag('self').name == 'child'
    other.clear_python_tag('self')
    root.get_child(0).clear_python_tag('self')


def test_node_subclass_persistent():
    class NodeSubclass(PandaNode):
        pass

    node = NodeSubclass('test_node_subclass')
    assert isinstance(node, PandaNode)

    # Always GC-tracked
    assert gc.is_tracked(node)

    # Registered type handle
    type_handle = node.get_type()
    assert type_handle.name == 'NodeSubclass'
    assert type_handle != PandaNode.get_class_type()
    assert tuple(type_handle.parent_classes) == (PandaNode.get_class_type(), )

    # Persistent wrapper
    parent = PandaNode('parent')
    parent.add_child(node)
    child = parent.get_child(0)
    assert child.this == node.this
    assert child is node
    assert type(child) is NodeSubclass
    parent = None
    child = None


def test_node_subclass_gc():
    class NodeSubclass(PandaNode):
        pass

    # Python wrapper destructs last
    with gc_disabled():
        node = NodeSubclass('test_node_subclass_gc1')

        assert node in gc.get_objects()

        node = None

        gc.collect()
        assert len(gc.garbage) == 1
        assert gc.garbage[0].name == 'test_node_subclass_gc1'

    # C++ reference destructs last
    with gc_disabled():
        node = NodeSubclass('test_node_subclass_gc2')
        parent = PandaNode('parent')
        parent.add_child(node)

        assert node in gc.get_objects()

        node = None

        # Hasn't been collected yet, since parent still holds a reference
        gc.collect()
        assert len(gc.garbage) == 0
        assert 'test_node_subclass_gc2' in [obj.name for obj in gc.get_objects() if isinstance(obj, PandaNode)]

        parent = None

        # Destructed without needing the GC
        assert 'test_node_subclass_gc2' not in [obj.name for obj in gc.get_objects() if isinstance(obj, PandaNode)]

        gc.collect()
        assert len(gc.garbage) == 0
