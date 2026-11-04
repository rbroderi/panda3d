/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file rayTraceFollower.I
 * @author rbroderi
 * @date 2026-11-03
 */

/**
 * Returns the scene whose instances this follower moves.
 */
INLINE RayTraceScene *RayTraceFollower::
get_scene() const {
  return _scene;
}

/**
 * Returns the node the instances are placed relative to (an empty NodePath:
 * the root of each node's own graph).
 */
INLINE const NodePath &RayTraceFollower::
get_relative_to() const {
  return _relative_to;
}

/**
 * Returns how many instances follow nodes.
 */
INLINE int RayTraceFollower::
get_num_instances() const {
  return (int)_follows.size();
}
