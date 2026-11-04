/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file pandaNode_ext.cxx
 * @author CFSworks
 * @date 2014-03-30
 */

#include "pandaNode_ext.h"

#ifdef HAVE_PYTHON

/**
 * A special Python method that is invoked by copy.copy(node).  Unlike the
 * PandaNode copy constructor, which creates a new node without children, this
 * shares child pointers (essentially making every child an instance).  This
 * is intended to simulate the behavior of copy.copy() for other objects.
 */
PT(PandaNode) Extension<PandaNode>::
__copy__() const {
  Thread *current_thread = Thread::get_current_thread();

  PT(PandaNode) node_dupe = _this->make_copy();

  PandaNode::Children children = _this->get_children(current_thread);
  int num_children = children.get_num_children();

  for (int i = 0; i < num_children; ++i) {
    node_dupe->add_child(children.get_child(i), children.get_child_sort(i));
  }

  return node_dupe;
}

/**
 * A special Python method that is invoked by copy.deepcopy(node).  This calls
 * copy_subgraph() unless the node is already present in the provided
 * dictionary.
 */
PyObject *Extension<PandaNode>::
__deepcopy__(PyObject *self, PyObject *memo) const {
  extern struct Dtool_PyTypedObject Dtool_PandaNode;

  PyObject *dupe;
  if (PyDict_GetItemRef(memo, self, &dupe) != 0) {
    // Already in the memo dictionary (or an error happened).
    return dupe;
  }

  PT(PandaNode) node_dupe = _this->copy_subgraph();

  // DTool_CreatePyInstanceTyped() steals a C++ reference.
  node_dupe->ref();
  dupe = DTool_CreatePyInstanceTyped
    ((void *)node_dupe.p(), Dtool_PandaNode, true, false,
     node_dupe->get_type_index());

  if (PyDict_SetItem(memo, self, dupe) != 0) {
    Py_DECREF(dupe);
    return nullptr;
  }

  return dupe;
}

/**
 * This variant on get_tag_keys returns a Python tuple of strings keys.
 */
PyObject *Extension<PandaNode>::
get_tag_keys() const {
  vector_string keys;
  _this->get_tag_keys(keys);

  PyObject *result = PyTuple_New(keys.size());
  for (size_t i = 0; i < keys.size(); ++i) {
    PyTuple_SET_ITEM(result, i, Dtool_WrapValue(keys[i]));
  }

  return result;
}

/**
 * Returns a dictionary of Python tags that is associated with the current
 * node.  This is similar to the regular tags, except this can store any
 * Python object instead of just a string.  However, the Python object is not
 * recorded to a bam file.
 */
PyObject *Extension<PandaNode>::
get_python_tags() {
  return Py_NewRef(do_get_python_tags());
}

/**
 * Associates an arbitrary Python object with a user-defined key which is
 * stored on the node.  This is similar to set_tag(), except it can store any
 * Python object instead of just a string.  However, the Python object is not
 * recorded to a bam file.
 *
 * Each unique key stores a different string value.  There is no effective
 * limit on the number of different keys that may be stored or on the length
 * of any one key's value.
 */
int Extension<PandaNode>::
set_python_tag(PyObject *key, PyObject *value) {
  return PyDict_SetItem(do_get_python_tags(), key, value);
}

/**
 * Retrieves the Python object that was previously set on this node for the
 * particular key, if any.  If no value has been previously set, returns None.
 */
PyObject *Extension<PandaNode>::
get_python_tag(PyObject *key) const {
  if (_this->_python_tag_data == nullptr) {
    return Py_NewRef(Py_None);
  }

  PyObject *dict = ((PythonTagDataImpl *)_this->_python_tag_data.p())->_dict;
  PyObject *value;
  if (PyDict_GetItemRef(dict, key, &value) == 0) {
    value = Py_NewRef(Py_None);
  }
  return value;
}

/**
 * Returns true if a Python object has been defined on this node for the
 * particular key (even if that object is None), or false if no object has
 * been set.
 */
bool Extension<PandaNode>::
has_python_tag(PyObject *key) const {
  if (_this->_python_tag_data == nullptr) {
    return false;
  }

  PyObject *dict = ((PythonTagDataImpl *)_this->_python_tag_data.p())->_dict;
  return PyDict_Contains(dict, key);
}

/**
 * Removes the Python object defined for this key on this particular node.
 * After a call to clear_python_tag(), has_python_tag() will return false for
 * the indicated key.
 */
void Extension<PandaNode>::
clear_python_tag(PyObject *key) {
  if (_this->_python_tag_data == nullptr) {
    return;
  }

  PyObject *dict = do_get_python_tags();
  Py_BEGIN_CRITICAL_SECTION(dict);
  if (PyDict_Contains(dict, key)) {
    PyDict_DelItem(dict, key);
  }

  if (PyDict_Size(dict) == 0 && Py_REFCNT(dict) == 1) {
    // This was the last tag, and do_get_python_tags() made sure we have a
    // unique reference to the tags, so clear the tag object.
    _this->_python_tag_data.clear();
  }
  Py_END_CRITICAL_SECTION();

  if (_this->_python_tag_data == nullptr) {
    update_wrapper_group(_this);
  }
}

/**
 * This variant on get_python_tag_keys returns a Python list of strings.
 */
PyObject *Extension<PandaNode>::
get_python_tag_keys() const {
  if (_this->_python_tag_data == nullptr) {
    return PyTuple_New(0);
  }

  PyObject *dict = ((PythonTagDataImpl *)_this->_python_tag_data.p())->_dict;
  return PyDict_Keys(dict);
}

/**
 * Called by Python to implement cycle detection.  The bindings only call this
 * from a wrapper that was counted with __add_wrapper__(), and only when every
 * reference to this node is held by such a wrapper.
 */
int Extension<PandaNode>::
__traverse__(visitproc visit, void *arg) {
  // To fully implement cycle breaking, we also have to recurse into all of
  // the node's children.  However, this seems like it would be potentially
  // quite expensive, so I'd rather not do it unless we had some optimization
  // that would allow us to quickly find out whether there are children with
  // Python tags.
  if (_this->_num_python_wrappers.load(std::memory_order_relaxed) > 1) {
    // Each of the wrappers will report a reference to the node's tags, but
    // the node only holds one.  Instead, each of them reports a reference to
    // the wrapper group, of which the node holds one per wrapper, and which
    // in turn reports the tags.  That way, the tags stay alive as long as any
    // one of the wrappers is reachable.
    PyObject *group = _this->_python_wrapper_group.load(std::memory_order_relaxed);
    Py_VISIT(group);
    return 0;
  }
  return traverse_python_tags(_this, visit, arg);
}

/**
 * Same as get_python_tags, without incrementing the reference count.
 */
PyObject *Extension<PandaNode>::
do_get_python_tags() {
  if (_this->_python_tag_data == nullptr) {
    _this->_python_tag_data = new PythonTagDataImpl;

    // If the node already has several wrappers, it now needs a group.
    PandaNode::_update_python_wrapper_group = &update_wrapper_group;
    if (_this->_num_python_wrappers.load(std::memory_order_relaxed) > 1) {
      update_wrapper_group(_this);
    }

  } else if (_this->_python_tag_data->get_ref_count() > 1) {
    // Copy-on-write.
    _this->_python_tag_data = new PythonTagDataImpl(*(PythonTagDataImpl *)_this->_python_tag_data.p());
  }
  return ((PythonTagDataImpl *)_this->_python_tag_data.p())->_dict;
}

/**
 * Reports the node's Python tags to the garbage collector.
 */
int Extension<PandaNode>::
traverse_python_tags(const PandaNode *node, visitproc visit, void *arg) {
  // If the tags are shared with a copy of the node (they are copied on
  // write), we can't tell whether that copy is alive, so we don't report
  // them.
  PandaNode::PythonTagData *tag_data = node->_python_tag_data;
  if (tag_data != nullptr && tag_data->get_ref_count() == 1) {
    Py_VISIT(((PythonTagDataImpl *)tag_data)->_dict);
  }
  return 0;
}

#ifndef CPPPARSER
namespace {
  // While a node with Python tags has two or more wrappers, the node holds
  // one reference to one of these for each wrapper.
  struct WrapperGroup {
    PyObject_HEAD
    const PandaNode *_node;
    int _refs;
  };

  PyTypeObject *wrapper_group_type = nullptr;

#ifdef Py_GIL_DISABLED
  PyMutex wrapper_group_lock = {0};
#endif
}
#endif  // CPPPARSER

/**
 * Called when a wrapper of the given node is added or removed, or the node's
 * tags are created or removed, while the node has two or more wrappers or a
 * wrapper group.  Makes the node hold one reference to its wrapper group per
 * wrapper while it has two or more wrappers and Python tags, and releases the
 * group otherwise.
 */
void Extension<PandaNode>::
update_wrapper_group(const PandaNode *node) {
#ifdef Py_GIL_DISABLED
  PyMutex_Lock(&wrapper_group_lock);
#endif

  int num_refs = 0;
  if (node->_python_tag_data != nullptr) {
    num_refs = node->_num_python_wrappers.load(std::memory_order_relaxed);
    if (num_refs < 2) {
      num_refs = 0;
    }
  }

  WrapperGroup *group = (WrapperGroup *)node->_python_wrapper_group.load(std::memory_order_relaxed);
  if (group == nullptr && num_refs > 0) {
    if (wrapper_group_type == nullptr) {
      static PyType_Slot slots[] = {
        {Py_tp_traverse, (void *)&wrapper_group_traverse},
        {Py_tp_dealloc, (void *)&wrapper_group_dealloc},
        {0, nullptr},
      };
      static PyType_Spec spec = {
        "panda3d.core.PandaNode._WrapperGroup",
        sizeof(WrapperGroup),
        0,
        Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
        slots,
      };
      wrapper_group_type = (PyTypeObject *)PyType_FromSpec(&spec);
    }
    if (wrapper_group_type != nullptr) {
      group = PyObject_GC_New(WrapperGroup, wrapper_group_type);
    }
    if (group != nullptr) {
      group->_node = node;
      group->_refs = 1;
      node->_python_wrapper_group.store((PyObject *)group, std::memory_order_relaxed);
      PyObject_GC_Track((PyObject *)group);
    } else {
      // Without a group, __traverse__ reports nothing, so the node's tags
      // can't be collected, but they stay alive.
      PyErr_Clear();
    }
  }

  if (group != nullptr) {
    while (group->_refs < num_refs) {
      Py_INCREF((PyObject *)group);
      ++group->_refs;
    }
    if (group->_refs > num_refs) {
      int release = group->_refs - num_refs;
      group->_refs = num_refs;
      if (num_refs == 0) {
        node->_python_wrapper_group.store(nullptr, std::memory_order_relaxed);
      }
      // The last of these deletes the group.
      while (release-- > 0) {
        Py_DECREF((PyObject *)group);
      }
    }
  }

#ifdef Py_GIL_DISABLED
  PyMutex_Unlock(&wrapper_group_lock);
#endif
}

/**
 * Reports the tags of the group's node to the garbage collector.
 */
int Extension<PandaNode>::
wrapper_group_traverse(PyObject *self, visitproc visit, void *arg) {
#if PY_VERSION_HEX >= 0x03090000
  Py_VISIT(Py_TYPE(self));
#endif
  return traverse_python_tags(((WrapperGroup *)self)->_node, visit, arg);
}

/**
 * Deletes a wrapper group, once the node has released all its references.
 */
void Extension<PandaNode>::
wrapper_group_dealloc(PyObject *self) {
  PyTypeObject *type = Py_TYPE(self);
  PyObject_GC_UnTrack(self);
  PyObject_GC_Del(self);
  Py_DECREF((PyObject *)type);
}

/**
 * Destroys the tags associated with the node.
 */
Extension<PandaNode>::PythonTagDataImpl::
~PythonTagDataImpl() {
#if defined(HAVE_THREADS) && !defined(SIMPLE_THREADS)
  // This might happen at any time, so be sure the Python state is ready for
  // it.
  PyGILState_STATE gstate;
  gstate = PyGILState_Ensure();
#endif

  Py_CLEAR(_dict);

#if defined(HAVE_THREADS) && !defined(SIMPLE_THREADS)
  PyGILState_Release(gstate);
#endif
}

#endif  // HAVE_PYTHON
