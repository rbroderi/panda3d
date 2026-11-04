/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceFollower.cxx
 * @author rbroderi
 * @date 2026-11-03
 */

#include "rayTraceFollower.h"

TypeHandle RayTraceFollower::_type_handle;

/**
 * Makes a follower of no instances yet, for the given scene.
 */
RayTraceFollower::
RayTraceFollower(RayTraceScene *scene, const NodePath &relative_to) :
  _scene(scene),
  _relative_to(relative_to)
{
  nassertv(scene != nullptr);
}

/**
 * Has the scene's nth instance follow the given node from now on.  Its
 * transform is taken to be where the node is now: the instance is moved the
 * next time update() finds the node somewhere else.  Several instances may
 * follow one node (one for each of a GeomNode's Geoms, say).
 */
void RayTraceFollower::
add_instance(int n, const NodePath &node) {
  nassertv(n >= 0 && n < _scene->get_num_instances());
  nassertv(!node.is_empty());

  Thread *current_thread = Thread::get_current_thread();
  if (!_relative_to.is_empty()) {
    _relative_net = _relative_to.get_net_transform(current_thread);
  }
  Follow follow;
  follow._instance = n;
  follow._node = node;
  follow._net = node.get_net_transform(current_thread);
  follow._transform = LCAST(float, _scene->get_instance_transform(n));
  _follows.push_back(std::move(follow));
}

/**
 * Forgets every instance: none follows a node any longer.
 */
void RayTraceFollower::
clear() {
  _follows.clear();
  _relative_net.clear();
}

/**
 * Moves each instance whose node is no longer where it was, relative to
 * relative_to.  Returns how many instances were moved.
 */
int RayTraceFollower::
update(Thread *current_thread) {
  CPT(TransformState) relative_net;
  if (!_relative_to.is_empty()) {
    relative_net = _relative_to.get_net_transform(current_thread);
  }
  bool relative_moved = (relative_net != _relative_net);
  _relative_net = relative_net;

  int moved = 0;
  const Follow *last = nullptr;
  for (Follow &follow : _follows) {
    // Instances of one node usually come one after another: the first one's
    // walk serves them all.
    CPT(TransformState) net;
    if (last != nullptr && last->_node == follow._node) {
      net = last->_net;
    } else {
      net = follow._node.get_net_transform(current_thread);
    }
    if (net != follow._net || relative_moved) {
      follow._net = net;
      CPT(TransformState) place = net;
      if (relative_net != nullptr) {
        place = relative_net->invert_compose(net);
      }
      LMatrix4f transform = LCAST(float, place->get_mat());
      if (transform != follow._transform) {
        follow._transform = transform;
        _scene->set_instance_transform(follow._instance, LCAST(PN_stdfloat, transform));
        ++moved;
      }
    }
    last = &follow;
  }
  return moved;
}
