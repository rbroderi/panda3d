/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file meshDrawNode.I
 * @author rbroderi
 * @date 2026-11-02
 */

/**
 * Adds a draw with the given number of work groups in the X, Y,
 * and Z dimensions.  Any of these values may be set to 1 if the respective
 * dimension should not be used.
 */
INLINE void MeshDrawNode::
add_draw(const LVecBase3i &num_groups) {
  Drawer::CDWriter cdata(_drawer->_cycler);
  cdata->_draws.push_back(num_groups);
}

/**
 * Adds a draw with the given number of work groups in the X, Y,
 * and Z dimensions.  Any of these values may be set to 1 if the respective
 * dimension should not be used.
 */
INLINE void MeshDrawNode::
add_draw(int num_groups_x, int num_groups_y, int num_groups_z) {
  LVecBase3i num_groups(num_groups_x, num_groups_y, num_groups_z);
  add_draw(num_groups);
}

/**
 * Removes all draws.
 */
INLINE void MeshDrawNode::
clear_draws() {
  Drawer::CDWriter cdata(_drawer->_cycler);
  cdata->_draws.clear();
}

/**
 * Returns the number of times add_draw has been called on this object.
 */
INLINE size_t MeshDrawNode::
get_num_draws() const {
  Drawer::CDReader cdata(_drawer->_cycler);
  return cdata->_draws.size();
}

/**
 * Returns the group counts of the nth draw associated with this object.
 */
INLINE const LVecBase3i &MeshDrawNode::
get_draw(size_t n) const {
  Drawer::CDReader cdata(_drawer->_cycler);
  nassertr(n < cdata->_draws.size(), LVecBase3i::zero());
  return cdata->_draws[n];
}

/**
 * Sets the group counts of the nth draw associated with this object.
 */
INLINE void MeshDrawNode::
set_draw(size_t n, const LVecBase3i &draw) {
  Drawer::CDWriter cdata(_drawer->_cycler);
  nassertv(n < cdata->_draws.size());
  cdata->_draws[n] = draw;
}

/**
 * Inserts a draw with the given number of work groups in the X,
 * Y, and Z dimensions at the given position in the list of draws.
 * Any of these values may be set to 1 if the respective dimension should not
 * be used.
 */
INLINE void MeshDrawNode::
insert_draw(size_t n, const LVecBase3i &draw) {
  Drawer::CDWriter cdata(_drawer->_cycler);
  if (n > cdata->_draws.size()) {
    n = cdata->_draws.size();
  }
  cdata->_draws.insert(cdata->_draws.begin() + n, draw);
}

/**
 * Erases the given draw index from the list.
 */
INLINE void MeshDrawNode::
remove_draw(size_t n) {
  Drawer::CDWriter cdata(_drawer->_cycler);
  nassertv(n < cdata->_draws.size());
  cdata->_draws.erase(cdata->_draws.begin() + n);
}

/**
 *
 */
INLINE MeshDrawNode::Drawer::CData::
CData() {
}

/**
 *
 */
INLINE MeshDrawNode::Drawer::CData::
CData(const MeshDrawNode::Drawer::CData &copy) :
  _draws(copy._draws)
{
}
